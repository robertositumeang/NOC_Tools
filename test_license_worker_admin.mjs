import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { test } from "node:test";
import { handleRequest } from "./cloudflare/worker.mjs";

globalThis.crypto ??= webcrypto;

class AdminDatabase {
  users = [];
  sessions = new Map();
  rateLimits = new Map();
  licenses = [];
  activations = [];
  activationHistory = [];

  prepare(sql) {
    const database = this;
    let values = [];
    const statement = {
      bind(...boundValues) {
        values = boundValues;
        return statement;
      },
      async first() {
        if (sql.includes("SELECT COUNT(*) AS admin_count")) {
          return {
            admin_count: database.users.filter((user) => user.role === "admin").length,
          };
        }
        if (sql.includes("SELECT blocked_until FROM auth_rate_limits")) {
          return database.rateLimits.get(values[0]) || null;
        }
        if (sql.includes("FROM admin_sessions") && sql.includes("JOIN users")) {
          const [tokenHash, now] = values;
          const session = database.sessions.get(tokenHash);
          const user = database.users.find(
            (item) => item.user_id === session?.user_id && item.role === "admin",
          );
          return session && session.expires_at > now && user?.is_active
            ? {
                user_id: user.user_id,
                username: user.username,
                display_name: user.display_name,
              }
            : null;
        }
        if (sql.includes("SELECT user_id, username, display_name, password_hash")) {
          const username = String(values[0]).toLowerCase();
          return (
            database.users.find(
              (user) =>
                user.username.toLowerCase() === username &&
                user.role === "admin" &&
                user.is_active === 1,
            ) || null
          );
        }
        if (sql.includes("SELECT display_name, password_hash")) {
          const username = String(values[0]).toLowerCase();
          return (
            database.users.find(
              (user) =>
                user.username.toLowerCase() === username &&
                user.role === "operator" &&
                user.is_active === 1,
            ) || null
          );
        }
        throw new Error(`Unexpected D1 first query: ${sql}`);
      },
      async all() {
        if (sql.includes("SELECT username, display_name, role, is_active")) {
          return {
            results: database.users.map(
              ({ username, display_name, role, is_active, created_at, updated_at }) => ({
                username,
                display_name,
                role,
                is_active,
                created_at,
                updated_at,
              }),
            ),
          };
        }
        if (sql.includes("FROM license_issues")) {
          const now = values[0];
          return {
            results: [...database.licenses]
              .reverse()
              .map((license) => {
                const history = database.activationHistory.find(
                  (entry) => entry.license_id === license.license_id,
                );
                return {
                  ...license,
                  activated_at: history?.activated_at ?? null,
                  expires_at: history?.expires_at ?? null,
                  status: !history
                    ? "not_activated"
                    : history.expires_at <= now
                      ? "expired"
                      : "active",
                };
              }),
          };
        }
        throw new Error(`Unexpected D1 all query: ${sql}`);
      },
      async run() {
        if (sql.includes("DELETE FROM license_issues")) {
          const [now] = values;
          const expiredIds = new Set(
            database.activationHistory
              .filter((entry) => entry.expires_at <= now)
              .map((entry) => entry.license_id),
          );
          const previousLength = database.licenses.length;
          database.licenses = database.licenses.filter(
            (license) => !expiredIds.has(license.license_id),
          );
          return {
            meta: { changes: previousLength - database.licenses.length },
          };
        }
        if (sql.includes("DELETE FROM license_activations")) {
          const [now] = values;
          const previousLength = database.activations.length;
          database.activations = database.activations.filter(
            (activation) => activation.expires_at > now,
          );
          return {
            meta: { changes: previousLength - database.activations.length },
          };
        }
        if (sql.includes("INSERT INTO auth_rate_limits")) {
          const [hash, timestamp] = values;
          const record = database.rateLimits.get(hash);
          if (!record || record.window_started_at <= timestamp - 900) {
            database.rateLimits.set(hash, {
              blocked_until: 0,
              window_started_at: timestamp,
              attempt_count: 1,
            });
          } else {
            record.attempt_count += 1;
            if (record.attempt_count >= 8) record.blocked_until = timestamp + 900;
          }
          return { meta: { changes: 1 } };
        }
        if (sql.includes("DELETE FROM auth_rate_limits")) {
          return { meta: { changes: Number(database.rateLimits.delete(values[0])) } };
        }
        if (sql.includes("INSERT INTO users") && sql.includes("WHERE NOT EXISTS")) {
          if (database.users.some((user) => user.role === "admin")) {
            return { meta: { changes: 0 } };
          }
          const [user_id, username, display_name, password_hash, created_at, updated_at] =
            values;
          database.users.push({
            user_id,
            username,
            display_name,
            password_hash,
            role: "admin",
            is_active: 1,
            created_at,
            updated_at,
          });
          return { meta: { changes: 1 } };
        }
        if (sql.includes("INSERT INTO admin_sessions")) {
          const [token_hash, user_id, expires_at, created_at] = values;
          database.sessions.set(token_hash, { user_id, expires_at, created_at });
          return { meta: { changes: 1 } };
        }
        if (sql.includes("DELETE FROM admin_sessions WHERE expires_at")) {
          const [now] = values;
          let changes = 0;
          for (const [key, session] of database.sessions) {
            if (session.expires_at <= now) {
              database.sessions.delete(key);
              changes += 1;
            }
          }
          return { meta: { changes } };
        }
        if (sql.includes("DELETE FROM admin_sessions WHERE token_hash")) {
          return { meta: { changes: Number(database.sessions.delete(values[0])) } };
        }
        if (sql.includes("INSERT INTO users") && sql.includes("VALUES")) {
          const [user_id, username, display_name, password_hash, role, created_at, updated_at] =
            values;
          if (database.users.some((user) => user.username.toLowerCase() === username.toLowerCase())) {
            throw new Error("UNIQUE constraint failed: users.username");
          }
          database.users.push({
            user_id,
            username,
            display_name,
            password_hash,
            role,
            is_active: 1,
            created_at,
            updated_at,
          });
          return { meta: { changes: 1 } };
        }
        if (sql.includes("UPDATE users SET password_hash")) {
          const [password_hash, updated_at, username] = values;
          const user = database.users.find(
            (item) => item.username.toLowerCase() === username.toLowerCase(),
          );
          if (!user) return { meta: { changes: 0 } };
          user.password_hash = password_hash;
          user.updated_at = updated_at;
          return { meta: { changes: 1 } };
        }
        if (sql.includes("UPDATE users SET is_active")) {
          const [is_active, updated_at, username] = values;
          const user = database.users.find(
            (item) =>
              item.username.toLowerCase() === username.toLowerCase() &&
              item.role === "operator",
          );
          if (!user) return { meta: { changes: 0 } };
          user.is_active = is_active;
          user.updated_at = updated_at;
          return { meta: { changes: 1 } };
        }
        if (sql.includes("INSERT INTO license_issues")) {
          const [license_id, email, machine_id, days_valid, license_type, operator, issued_at] =
            values;
          database.licenses.push({
            license_id,
            email,
            machine_id,
            days_valid,
            license_type,
            operator,
            issued_at,
          });
          return { meta: { changes: 1 } };
        }
        throw new Error(`Unexpected D1 run query: ${sql}`);
      },
    };
    return statement;
  }

  async batch(statements) {
    return Promise.all(statements.map((statement) => statement.run()));
  }
}

async function createFixture() {
  const keys = await webcrypto.subtle.generateKey("Ed25519", true, ["sign", "verify"]);
  const publicKey = new Uint8Array(
    await webcrypto.subtle.exportKey("raw", keys.publicKey),
  );
  const privateDer = new Uint8Array(
    await webcrypto.subtle.exportKey("pkcs8", keys.privateKey),
  );
  const privatePem = `-----BEGIN PRIVATE KEY-----\n${Buffer.from(privateDer)
    .toString("base64")
    .match(/.{1,64}/g)
    .join("\n")}\n-----END PRIVATE KEY-----`;
  const db = new AdminDatabase();
  const env = {
    DB: db,
    ADMIN_BOOTSTRAP_SECRET: "initial-setup-secret",
    LICENSE_SIGNING_PRIVATE_KEY: privatePem,
  };
  const now = 1_800_000_000;
  const call = async (path, { method = "GET", payload, token } = {}) => {
    const headers = {};
    if (payload) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;
    const request = new Request(`https://license.example.workers.dev${path}`, {
      method,
      headers,
      body: payload ? JSON.stringify(payload) : undefined,
    });
    const response = await handleRequest(request, env, {
      publicKeyHex: Buffer.from(publicKey).toString("hex"),
      nowSeconds: () => now,
    });
    return { response, body: await response.json() };
  };
  return { call, db, keys, now };
}

async function createAdminSession(fixture) {
  await fixture.call("/v1/admin/bootstrap", {
    method: "POST",
    payload: {
      bootstrap_secret: "initial-setup-secret",
      username: "admin",
      display_name: "NOC Administrator",
      password: "StrongAdminPassword!2026",
    },
  });
  const { body } = await fixture.call("/v1/admin/login", {
    method: "POST",
    payload: { username: "admin", password: "StrongAdminPassword!2026" },
  });
  return body.token;
}

test("adminBootstrap_isSingleUse_andAdminSessionProtectsUserListing", async () => {
  const fixture = await createFixture();
  const status = await fixture.call("/v1/admin/status");
  assert.deepEqual(status.body, { bootstrap_required: true });

  const bootstrap = await fixture.call("/v1/admin/bootstrap", {
    method: "POST",
    payload: {
      bootstrap_secret: "initial-setup-secret",
      username: "admin",
      display_name: "NOC Administrator",
      password: "StrongAdminPassword!2026",
    },
  });
  assert.equal(bootstrap.response.status, 200);
  assert.equal(fixture.db.users[0].password_hash.split("$")[1], "100000");

  const repeated = await fixture.call("/v1/admin/bootstrap", {
    method: "POST",
    payload: {
      bootstrap_secret: "initial-setup-secret",
      username: "other-admin",
      display_name: "Other Admin",
      password: "OtherStrongPassword!2026",
    },
  });
  assert.equal(repeated.response.status, 409);

  const unauthenticated = await fixture.call("/v1/admin/users");
  assert.equal(unauthenticated.response.status, 401);

  const login = await fixture.call("/v1/admin/login", {
    method: "POST",
    payload: { username: "admin", password: "StrongAdminPassword!2026" },
  });
  assert.equal(login.response.status, 200);
  assert.equal(typeof login.body.token, "string");

  const users = await fixture.call("/v1/admin/users", { token: login.body.token });
  assert.equal(users.response.status, 200);
  assert.deepEqual(users.body.users.map((user) => user.username), ["admin"]);

  const logout = await fixture.call("/v1/admin/logout", {
    method: "POST",
    token: login.body.token,
  });
  assert.deepEqual(logout.body, { logged_out: true });
  const expiredSession = await fixture.call("/v1/admin/users", {
    token: login.body.token,
  });
  assert.equal(expiredSession.response.status, 401);
});

test("operatorAccount_canBeCreatedResetDeactivatedAndReactivated", async () => {
  const fixture = await createFixture();
  const token = await createAdminSession(fixture);
  const created = await fixture.call("/v1/admin/users", {
    method: "POST",
    token,
    payload: {
      username: "operator",
      display_name: "NOC Operator",
      password: "InitialOperatorPassword!2026",
      role: "operator",
    },
  });
  assert.equal(created.response.status, 200);

  const firstLogin = await fixture.call("/v1/login", {
    method: "POST",
    payload: { username: "operator", password: "InitialOperatorPassword!2026" },
  });
  assert.deepEqual(firstLogin.body, {
    authenticated: true,
    display_name: "NOC Operator",
  });

  const reset = await fixture.call("/v1/admin/users/password", {
    method: "POST",
    token,
    payload: { username: "operator", password: "ReplacementPassword!2026" },
  });
  assert.equal(reset.response.status, 200);
  const status = await fixture.call("/v1/admin/users/status", {
    method: "POST",
    token,
    payload: { username: "operator", active: false },
  });
  assert.equal(status.response.status, 200);

  const inactiveLogin = await fixture.call("/v1/login", {
    method: "POST",
    payload: { username: "operator", password: "ReplacementPassword!2026" },
  });
  assert.equal(inactiveLogin.response.status, 401);
  await fixture.call("/v1/admin/users/status", {
    method: "POST",
    token,
    payload: { username: "operator", active: true },
  });
  const reactivatedLogin = await fixture.call("/v1/login", {
    method: "POST",
    payload: { username: "operator", password: "ReplacementPassword!2026" },
  });
  assert.equal(reactivatedLogin.response.status, 200);
});

test("adminLicenseIssuance_signsKeyAndListsAuditRecord", async () => {
  const fixture = await createFixture();
  const token = await createAdminSession(fixture);
  const issued = await fixture.call("/v1/admin/licenses/issue", {
    method: "POST",
    token,
    payload: {
      email: "operator@example.com",
      machine_id: "NOC-AAAA-BBBB-CCCC-DDDD",
      days: 60,
      operator: "NOC_Operator",
    },
  });
  assert.equal(issued.response.status, 200);
  assert.match(issued.body.license_key, /^NOC-LIC3-/);
  assert.equal(issued.body.email, "operator@example.com");
  assert.equal(issued.body.machine_id, "NOC-AAAA-BBBB-CCCC-DDDD");
  assert.equal(issued.body.days, 60);

  const blob = Buffer.from(
    issued.body.license_key.slice("NOC-LIC3-".length),
    "base64url",
  );
  const payloadBytes = blob.subarray(0, blob.length - 64);
  const signature = blob.subarray(blob.length - 64);
  assert.equal(
    await webcrypto.subtle.verify(
      "Ed25519",
      fixture.keys.publicKey,
      signature,
      payloadBytes,
    ),
    true,
  );
  const licensePayload = JSON.parse(new TextDecoder().decode(payloadBytes));
  assert.equal(licensePayload.email, "operator@example.com");
  assert.equal(licensePayload.mid, "NOC-AAAA-BBBB-CCCC-DDDD");
  assert.equal(licensePayload.days, 60);

  const history = await fixture.call("/v1/admin/licenses", { token });
  assert.equal(history.response.status, 200);
  assert.equal(history.body.licenses.length, 1);
  assert.equal(history.body.licenses[0].license_id, licensePayload.jti);
});

test("adminLicenseListing_marksExpiredAtBoundaryAndKeepsUnactivatedPending", async () => {
  const fixture = await createFixture();
  const token = await createAdminSession(fixture);
  const now = fixture.now;
  fixture.db.licenses = [
    { license_id: "old", email: "old@example.com", issued_at: now - 100 },
    { license_id: "boundary", email: "boundary@example.com", issued_at: now - 50 },
    { license_id: "active", email: "active@example.com", issued_at: now - 20 },
    { license_id: "pending", email: "pending@example.com", issued_at: now },
  ];
  fixture.db.activationHistory = [
    { license_id: "old", activated_at: now - 20, expires_at: now - 1 },
    { license_id: "boundary", activated_at: now - 10, expires_at: now },
    { license_id: "active", activated_at: now - 10, expires_at: now + 1 },
  ];

  const response = await fixture.call("/v1/admin/licenses", { token });

  assert.equal(response.response.status, 200);
  assert.deepEqual(
    response.body.licenses.map(({ license_id, status }) => [license_id, status]),
    [
      ["pending", "not_activated"],
      ["active", "active"],
      ["boundary", "expired"],
      ["old", "expired"],
    ],
  );
  assert.equal(response.body.licenses[2].expires_at, now);
});

test("adminExpiredLicenseCleanup_requiresAdminAndPreservesActivationHistory", async () => {
  const fixture = await createFixture();
  const now = fixture.now;
  fixture.db.licenses = [
    { license_id: "expired", email: "expired@example.com" },
    { license_id: "active", email: "active@example.com" },
    { license_id: "pending", email: "pending@example.com" },
  ];
  fixture.db.activations = [
    { license_id: "expired", expires_at: now },
    { license_id: "active", expires_at: now + 1 },
  ];
  fixture.db.activationHistory = [
    { license_id: "expired", expires_at: now },
    { license_id: "active", expires_at: now + 1 },
  ];

  const unauthenticated = await fixture.call("/v1/admin/licenses/expired", {
    method: "DELETE",
  });
  assert.equal(unauthenticated.response.status, 401);
  assert.equal(fixture.db.licenses.length, 3);

  const token = await createAdminSession(fixture);
  const response = await fixture.call("/v1/admin/licenses/expired", {
    method: "DELETE",
    token,
  });

  assert.equal(response.response.status, 200);
  assert.deepEqual(response.body, {
    deleted_licenses: 1,
    cleared_activations: 1,
  });
  assert.deepEqual(
    fixture.db.licenses.map((license) => license.license_id),
    ["active", "pending"],
  );
  assert.deepEqual(
    fixture.db.activations.map((activation) => activation.license_id),
    ["active"],
  );
  assert.deepEqual(
    fixture.db.activationHistory.map((history) => history.license_id),
    ["expired", "active"],
  );
});
