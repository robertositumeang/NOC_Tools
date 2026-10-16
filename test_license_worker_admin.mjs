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
      sql,
      get values() {
        return values;
      },
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
          if (sql.includes("email COLLATE NOCASE IN")) {
            const emails = new Set(values.map((email) => String(email).toLowerCase()));
            const previousLength = database.licenses.length;
            database.licenses = database.licenses.filter(
              (license) => !emails.has(license.email.toLowerCase()),
            );
            return {
              meta: { changes: previousLength - database.licenses.length },
            };
          }
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
          if (sql.includes("email COLLATE NOCASE IN")) {
            const emails = new Set(values.map((email) => String(email).toLowerCase()));
            const previousLength = database.activations.length;
            database.activations = database.activations.filter(
              (activation) => !emails.has(activation.email.toLowerCase()),
            );
            return {
              meta: { changes: previousLength - database.activations.length },
            };
          }
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
    if (statements[0].sql.includes("INSERT OR IGNORE INTO license_activation_history")) {
      const [
        licenseId,
        email,
        machineId,
        activatedAt,
        expiresAt,
        activationToken,
        boundEmail,
        requestedMachine,
      ] = statements[0].values;
      const currentForEmail = this.activations.find(
        (activation) => activation.email.toLowerCase() === boundEmail,
      );
      let history = this.activationHistory.find(
        (entry) => entry.license_id === licenseId,
      );
      if (
        !history &&
        (!currentForEmail || currentForEmail.machine_id === requestedMachine)
      ) {
        history = {
          license_id: licenseId,
          email,
          machine_id: machineId,
          activated_at: activatedAt,
          expires_at: expiresAt,
          activation_token: activationToken,
        };
        this.activationHistory.push(history);
      }

      const [currentLicenseId, currentToken] = statements[1].values;
      const currentHistory = this.activationHistory.find(
        (entry) =>
          entry.license_id === currentLicenseId &&
          entry.activation_token === currentToken,
      );
      if (currentHistory) {
        const currentIndex = this.activations.findIndex(
          (activation) =>
            activation.email.toLowerCase() === currentHistory.email,
        );
        if (currentIndex < 0) {
          this.activations.push({ ...currentHistory });
        } else if (
          this.activations[currentIndex].machine_id === currentHistory.machine_id &&
          this.activations[currentIndex].license_id !== currentHistory.license_id
        ) {
          this.activations[currentIndex] = { ...currentHistory };
        }
      }

      const selectedHistory = this.activationHistory.find(
        (entry) => entry.license_id === statements[2].values[0],
      );
      const selectedCurrent = this.activations.find(
        (activation) =>
          activation.email.toLowerCase() === statements[3].values[0],
      );
      return [
        { success: true },
        { success: true },
        { success: true, results: selectedHistory ? [selectedHistory] : [] },
        { success: true, results: selectedCurrent ? [selectedCurrent] : [] },
      ];
    }
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
  assert.equal(history.body.licenses[0].license_key, issued.body.license_key);
});

test("adminPendingLicenseListing_recoversTheOriginalSignedKey", async () => {
  const fixture = await createFixture();
  const token = await createAdminSession(fixture);
  const issued = await fixture.call("/v1/admin/licenses/issue", {
    method: "POST",
    token,
    payload: {
      email: "pending@example.com",
      machine_id: "NOC-AAAA-BBBB-CCCC-DDDD",
      days: 30,
      operator: "NOC_Operator",
    },
  });

  const listed = await fixture.call("/v1/admin/licenses", { token });
  const pending = listed.body.licenses[0];
  const blob = Buffer.from(
    pending.license_key.slice("NOC-LIC3-".length),
    "base64url",
  );
  const payloadBytes = blob.subarray(0, blob.length - 64);
  const signature = blob.subarray(blob.length - 64);

  assert.equal(issued.response.status, 200);
  assert.equal(listed.response.status, 200);
  assert.equal(pending.status, "not_activated");
  assert.equal(pending.license_key, issued.body.license_key);
  assert.equal(
    await webcrypto.subtle.verify(
      "Ed25519",
      fixture.keys.publicKey,
      signature,
      payloadBytes,
    ),
    true,
  );
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
  assert.match(response.body.licenses[0].license_key, /^NOC-LIC3-/);
  assert.equal(response.body.licenses[1].license_key, undefined);
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

test("adminSelectedEmailCleanup_unbindsOnlySelectedEmailsAndPreservesHistory", async () => {
  const fixture = await createFixture();
  const token = await createAdminSession(fixture);
  fixture.db.licenses = [
    { license_id: "old-key", email: "same@example.com" },
    { license_id: "new-key", email: "same@example.com" },
    { license_id: "other-key", email: "other@example.com" },
  ];
  fixture.db.activations = [
    {
      email: "same@example.com",
      license_id: "old-key",
      machine_id: "OLD-DEVICE",
      expires_at: fixture.now + 1000,
    },
    {
      email: "other@example.com",
      license_id: "other-key",
      machine_id: "OTHER-DEVICE",
      expires_at: fixture.now + 1000,
    },
  ];
  fixture.db.activationHistory = [
    { license_id: "old-key", email: "same@example.com", expires_at: fixture.now + 1000 },
  ];

  const response = await fixture.call("/v1/admin/licenses/by-email", {
    method: "DELETE",
    token,
    payload: { emails: [" SAME@example.com ", "same@example.com"] },
  });

  assert.equal(response.response.status, 200);
  assert.deepEqual(response.body, {
    deleted_licenses: 2,
    cleared_activations: 1,
  });
  assert.deepEqual(fixture.db.licenses, [
    { license_id: "other-key", email: "other@example.com" },
  ]);
  assert.deepEqual(
    fixture.db.activations.map((activation) => activation.email),
    ["other@example.com"],
  );
  assert.deepEqual(
    fixture.db.activationHistory.map((entry) => entry.license_id),
    ["old-key"],
  );
});

test("adminSelectedEmailCleanup_allowsFreshLicenseForNewDeviceAndRetainsOldReplayGuard", async () => {
  const fixture = await createFixture();
  const token = await createAdminSession(fixture);
  fixture.db.activations = [
    {
      email: "shared@example.com",
      license_id: "old-license",
      machine_id: "OLD-DEVICE",
      expires_at: fixture.now + 1000,
      activation_token: "old-activation-proof",
    },
  ];
  fixture.db.activationHistory = [
    {
      license_id: "old-license",
      email: "shared@example.com",
      machine_id: "OLD-DEVICE",
      activated_at: fixture.now - 100,
      expires_at: fixture.now + 1000,
      activation_token: "old-activation-proof",
    },
  ];
  const issue = async () =>
    fixture.call("/v1/admin/licenses/issue", {
      method: "POST",
      token,
      payload: {
        email: "shared@example.com",
        machine_id: "NEW-DEVICE",
        days: 30,
        operator: "NOC_Operator",
      },
    });
  const activate = async (licenseKey) =>
    fixture.call("/v1/activate", {
      method: "POST",
      payload: {
        email: "shared@example.com",
        machine_id: "NEW-DEVICE",
        license_key: licenseKey,
      },
    });

  const firstIssued = await issue();
  const blocked = await activate(firstIssued.body.license_key);
  assert.equal(blocked.response.status, 409);
  assert.match(blocked.body.detail, /Email ini sudah terikat ke perangkat lain/);

  const cleared = await fixture.call("/v1/admin/licenses/by-email", {
    method: "DELETE",
    token,
    payload: { emails: ["shared@example.com"] },
  });
  assert.equal(cleared.response.status, 200);
  assert.equal(fixture.db.activations.length, 0);
  assert.equal(fixture.db.activationHistory.length, 1);

  const replacementIssued = await issue();
  const activated = await activate(replacementIssued.body.license_key);
  const replacementBlob = Buffer.from(
    replacementIssued.body.license_key.slice("NOC-LIC3-".length),
    "base64url",
  );
  const replacementPayload = JSON.parse(
    new TextDecoder().decode(replacementBlob.subarray(0, replacementBlob.length - 64)),
  );
  assert.equal(activated.response.status, 200);
  assert.equal(fixture.db.activations[0].machine_id, "NEW-DEVICE");
  assert.deepEqual(
    fixture.db.activationHistory.map(({ license_id }) => license_id),
    ["old-license", replacementPayload.jti],
  );
});

test("adminSelectedEmailCleanup_requiresAdminAndValidNonemptyEmails", async () => {
  const fixture = await createFixture();
  fixture.db.licenses = [{ license_id: "key", email: "user@example.com" }];
  const unauthenticated = await fixture.call("/v1/admin/licenses/by-email", {
    method: "DELETE",
    payload: { emails: ["user@example.com"] },
  });
  assert.equal(unauthenticated.response.status, 401);
  assert.equal(fixture.db.licenses.length, 1);

  const token = await createAdminSession(fixture);
  for (const emails of [
    [],
    ["not-an-email"],
    "user@example.com",
    Array.from({ length: 51 }, (_, index) => `user${index}@example.com`),
  ]) {
    const response = await fixture.call("/v1/admin/licenses/by-email", {
      method: "DELETE",
      token,
      payload: { emails },
    });
    assert.equal(response.response.status, 400);
    assert.equal(fixture.db.licenses.length, 1);
  }
});
