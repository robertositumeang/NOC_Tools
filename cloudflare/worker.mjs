const LICENSE_PUBLIC_KEY_HEX =
  "e6105a319dce7c2dd20803b48fa5a18cd15290f26dbb1da3e3642e6b58bdf274";
const LICENSE_PREFIX = "NOC-LIC3-";
const ACTIVATION_PREFIX = "NOC-ACT1-";
const ADMIN_SESSION_SECONDS = 8 * 60 * 60;
const PASSWORD_ITERATIONS = 100_000;
const MAX_BODY_BYTES = 16 * 1024;
const encoder = new TextEncoder();

class ApiError extends Error {
  constructor(message, status = 400) {
    super(message);
    this.status = status;
  }
}

function jsonResponse(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/json; charset=utf-8",
      "X-Content-Type-Options": "nosniff",
    },
  });
}

function hexToBytes(hex) {
  if (!/^(?:[0-9a-f]{2})+$/i.test(hex)) {
    throw new ApiError("Konfigurasi public key tidak valid.", 503);
  }
  return Uint8Array.from(hex.match(/.{2}/g), (byte) => Number.parseInt(byte, 16));
}

function base64UrlToBytes(value) {
  if (!value || value.length > 8192 || !/^[A-Za-z0-9_-]+$/.test(value)) {
    throw new ApiError("Format karakter lisensi tidak valid.");
  }
  const base64 = value.replace(/-/g, "+").replace(/_/g, "/");
  try {
    const decoded = atob(base64 + "=".repeat((4 - (base64.length % 4)) % 4));
    return Uint8Array.from(decoded, (character) => character.charCodeAt(0));
  } catch {
    throw new ApiError("Format karakter lisensi tidak valid.");
  }
}

function bytesToBase64Url(value) {
  let binary = "";
  for (const byte of value) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function normalizeEmail(value) {
  if (typeof value !== "string") {
    throw new ApiError("Alamat email tidak valid.");
  }
  const email = value.trim().toLowerCase();
  if (
    email.length > 254 ||
    !/^[^@\s]+@[^@\s]+\.[^@\s]+$/u.test(email)
  ) {
    throw new ApiError("Alamat email tidak valid.");
  }
  return email;
}

async function readJsonBody(request) {
  const contentType = (request.headers.get("Content-Type") || "")
    .split(";")[0]
    .trim()
    .toLowerCase();
  if (contentType !== "application/json") {
    throw new ApiError("Permintaan harus menggunakan application/json.", 415);
  }

  if (!request.body) {
    throw new ApiError("Body permintaan tidak valid.");
  }

  const reader = request.body.getReader();
  const chunks = [];
  let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > MAX_BODY_BYTES) {
      await reader.cancel();
      throw new ApiError("Ukuran permintaan terlalu besar.", 413);
    }
    chunks.push(value);
  }

  const bodyBytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) {
    bodyBytes.set(chunk, offset);
    offset += chunk.byteLength;
  }

  let body;
  try {
    body = JSON.parse(
      new TextDecoder("utf-8", { fatal: true, ignoreBOM: false }).decode(bodyBytes),
    );
  } catch {
    throw new ApiError("Body permintaan bukan JSON yang valid.");
  }
  if (!isRecord(body)) {
    throw new ApiError("Body permintaan tidak valid.");
  }
  return body;
}

async function decodeIssuedLicense(token, publicKeyHex) {
  if (typeof token !== "string" || !token.startsWith(LICENSE_PREFIX)) {
    throw new ApiError("Format token lisensi tidak didukung.");
  }
  const blob = base64UrlToBytes(token.slice(LICENSE_PREFIX.length));
  if (blob.length <= 64) {
    throw new ApiError("Ukuran paket lisensi tidak valid.");
  }

  const payloadBytes = blob.subarray(0, blob.length - 64);
  const signature = blob.subarray(blob.length - 64);
  let publicKey;
  try {
    publicKey = await crypto.subtle.importKey(
      "raw",
      hexToBytes(publicKeyHex),
      { name: "Ed25519" },
      false,
      ["verify"],
    );
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError("Public key layanan aktivasi tidak valid.", 503);
  }

  let verified = false;
  try {
    verified = await crypto.subtle.verify(
      "Ed25519",
      publicKey,
      signature,
      payloadBytes,
    );
  } catch {
    throw new ApiError("Format token lisensi tidak valid.");
  }
  if (!verified) {
    throw new ApiError("Tanda tangan digital lisensi tidak sah atau data rusak.");
  }

  let payload;
  try {
    payload = JSON.parse(
      new TextDecoder("utf-8", { fatal: true, ignoreBOM: false }).decode(payloadBytes),
    );
  } catch {
    throw new ApiError("Payload lisensi tidak valid.");
  }
  if (!isRecord(payload)) {
    throw new ApiError("Payload lisensi tidak valid.");
  }
  return payload;
}

async function importSigningKey(pem, publicKeyHex) {
  if (typeof pem !== "string" || !pem.trim()) {
    throw new ApiError("Signing key layanan aktivasi tidak tersedia.", 503);
  }
  const encoded = pem
    .replace(/-----BEGIN PRIVATE KEY-----|-----END PRIVATE KEY-----|\s/g, "");
  let keyBytes;
  try {
    const binary = atob(encoded);
    keyBytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
  } catch {
    throw new ApiError("Signing key layanan aktivasi tidak valid.", 503);
  }

  let signingKey;
  try {
    signingKey = await crypto.subtle.importKey(
      "pkcs8",
      keyBytes,
      { name: "Ed25519" },
      false,
      ["sign"],
    );
  } catch {
    throw new ApiError("Signing key layanan aktivasi tidak valid.", 503);
  }

  const publicKey = await crypto.subtle.importKey(
    "raw",
    hexToBytes(publicKeyHex),
    { name: "Ed25519" },
    false,
    ["verify"],
  );
  const challenge = encoder.encode("NOC-License-Signing-Key-Check-v1");
  const signature = await crypto.subtle.sign("Ed25519", signingKey, challenge);
  if (!(await crypto.subtle.verify("Ed25519", publicKey, signature, challenge))) {
    throw new ApiError(
      "Signing key layanan tidak cocok dengan aplikasi yang terpasang.",
      503,
    );
  }
  return signingKey;
}

async function signActivation(payload, signingKey) {
  const payloadBytes = encoder.encode(JSON.stringify(payload));
  const signature = new Uint8Array(
    await crypto.subtle.sign("Ed25519", signingKey, payloadBytes),
  );
  const signedBlob = new Uint8Array(payloadBytes.length + signature.length);
  signedBlob.set(payloadBytes);
  signedBlob.set(signature, payloadBytes.length);
  return ACTIVATION_PREFIX + bytesToBase64Url(signedBlob);
}

function constantTimeEqual(left, right) {
  const leftBytes = encoder.encode(left);
  const rightBytes = encoder.encode(right);
  let difference = leftBytes.length ^ rightBytes.length;
  const length = Math.max(leftBytes.length, rightBytes.length);
  for (let index = 0; index < length; index += 1) {
    difference |= (leftBytes[index] || 0) ^ (rightBytes[index] || 0);
  }
  return difference === 0;
}

function randomToken(byteLength = 32) {
  const bytes = crypto.getRandomValues(new Uint8Array(byteLength));
  return bytesToBase64Url(bytes);
}

async function digestHex(value) {
  const digest = new Uint8Array(
    await crypto.subtle.digest("SHA-256", encoder.encode(value)),
  );
  return Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function hashPassword(password, salt = crypto.getRandomValues(new Uint8Array(16))) {
  if (typeof password !== "string" || password.length < 12 || password.length > 256) {
    throw new ApiError("Kata sandi harus terdiri dari 12 sampai 256 karakter.");
  }
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    encoder.encode(password),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const derived = new Uint8Array(
    await crypto.subtle.deriveBits(
      {
        name: "PBKDF2",
        hash: "SHA-256",
        salt,
        iterations: PASSWORD_ITERATIONS,
      },
      keyMaterial,
      256,
    ),
  );
  return `pbkdf2-sha256$${PASSWORD_ITERATIONS}$${bytesToBase64Url(salt)}$${bytesToBase64Url(derived)}`;
}

async function verifyPassword(password, storedHash) {
  if (
    typeof password !== "string" ||
    password.length > 256 ||
    typeof storedHash !== "string"
  ) {
    return false;
  }
  const [algorithm, rawIterations, encodedSalt, encodedExpected, extra] =
    storedHash.split("$");
  const iterations = Number(rawIterations);
  if (
    extra !== undefined ||
    algorithm !== "pbkdf2-sha256" ||
    !Number.isSafeInteger(iterations) ||
    iterations < 100_000 ||
    iterations > 1_000_000
  ) {
    return false;
  }
  let salt;
  let expected;
  try {
    salt = base64UrlToBytes(encodedSalt);
    expected = base64UrlToBytes(encodedExpected);
  } catch {
    return false;
  }
  if (salt.length !== 16 || expected.length !== 32) return false;
  const material = await crypto.subtle.importKey(
    "raw",
    encoder.encode(password),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const actual = new Uint8Array(
    await crypto.subtle.deriveBits(
      { name: "PBKDF2", hash: "SHA-256", salt, iterations },
      material,
      256,
    ),
  );
  let difference = 0;
  for (let index = 0; index < expected.length; index += 1) {
    difference |= actual[index] ^ expected[index];
  }
  return difference === 0;
}

function requireDatabase(env) {
  if (!env.DB || typeof env.DB.prepare !== "function") {
    throw new ApiError("Database layanan tidak tersedia.", 503);
  }
  return env.DB;
}

async function rateLimitScope(request, username) {
  const address = request.headers.get("CF-Connecting-IP") || "unknown";
  return digestHex(`${username.toLowerCase()}\n${address}`);
}

async function checkLoginRateLimit(db, scopeHash, nowSeconds) {
  const record = await db
    .prepare(
      "SELECT blocked_until FROM auth_rate_limits WHERE scope_hash = ? LIMIT 1",
    )
    .bind(scopeHash)
    .first();
  if (record && record.blocked_until > nowSeconds()) {
    throw new ApiError("Terlalu banyak percobaan login. Coba lagi nanti.", 429);
  }
}

async function recordLoginFailure(db, scopeHash, nowSeconds) {
  const timestamp = nowSeconds();
  await db
    .prepare(
      `INSERT INTO auth_rate_limits
        (scope_hash, window_started_at, attempt_count, blocked_until)
       VALUES (?, ?, 1, 0)
       ON CONFLICT(scope_hash) DO UPDATE SET
         window_started_at = CASE
           WHEN auth_rate_limits.window_started_at <= ? THEN excluded.window_started_at
           ELSE auth_rate_limits.window_started_at
         END,
         attempt_count = CASE
           WHEN auth_rate_limits.window_started_at <= ? THEN 1
           ELSE auth_rate_limits.attempt_count + 1
         END,
         blocked_until = CASE
           WHEN auth_rate_limits.window_started_at <= ? THEN 0
           WHEN auth_rate_limits.attempt_count + 1 >= 8 THEN excluded.window_started_at + 900
           ELSE auth_rate_limits.blocked_until
         END`,
    )
    .bind(scopeHash, timestamp, timestamp - 900, timestamp - 900, timestamp - 900)
    .run();
}

async function clearLoginFailures(db, scopeHash) {
  await db
    .prepare("DELETE FROM auth_rate_limits WHERE scope_hash = ?")
    .bind(scopeHash)
    .run();
}

async function getAdminFromSession(request, env, nowSeconds) {
  const authorization = request.headers.get("Authorization") || "";
  const match = /^Bearer ([A-Za-z0-9_-]{40,128})$/.exec(authorization);
  if (!match) throw new ApiError("Sesi administrator tidak valid.", 401);

  const tokenHash = await digestHex(match[1]);
  const admin = await requireDatabase(env)
    .prepare(
      `SELECT users.user_id, users.username, users.display_name
       FROM admin_sessions
       JOIN users ON users.user_id = admin_sessions.user_id
       WHERE admin_sessions.token_hash = ?
         AND admin_sessions.expires_at > ?
         AND users.role = 'admin'
         AND users.is_active = 1
       LIMIT 1`,
    )
    .bind(tokenHash, nowSeconds())
    .first();
  if (!admin) throw new ApiError("Sesi administrator kedaluwarsa atau tidak valid.", 401);
  return admin;
}

async function adminBootstrap(request, env, nowSeconds) {
  if (typeof env.ADMIN_BOOTSTRAP_SECRET !== "string" || !env.ADMIN_BOOTSTRAP_SECRET) {
    throw new ApiError("Setup awal administrator belum dikonfigurasi.", 503);
  }
  const body = await readJsonBody(request);
  if (
    typeof body.bootstrap_secret !== "string" ||
    !constantTimeEqual(body.bootstrap_secret, env.ADMIN_BOOTSTRAP_SECRET)
  ) {
    throw new ApiError("Setup awal administrator ditolak.", 403);
  }
  const username = typeof body.username === "string" ? body.username.trim() : "";
  const displayName =
    typeof body.display_name === "string" ? body.display_name.trim() : "";
  if (!/^[A-Za-z0-9_.-]{3,64}$/.test(username) || !displayName || displayName.length > 100) {
    throw new ApiError("Username atau nama administrator tidak valid.");
  }
  const passwordHash = await hashPassword(body.password);
  const userId = crypto.randomUUID();
  const timestamp = nowSeconds();
  const result = await requireDatabase(env)
    .prepare(
      `INSERT INTO users
        (user_id, username, display_name, password_hash, role, is_active, created_at, updated_at)
       SELECT ?, ?, ?, ?, 'admin', 1, ?, ?
       WHERE NOT EXISTS (SELECT 1 FROM users WHERE role = 'admin')`,
    )
    .bind(userId, username, displayName, passwordHash, timestamp, timestamp)
    .run();
  if (result.meta?.changes !== 1) {
    throw new ApiError("Administrator awal sudah dibuat.", 409);
  }
  return { created: true };
}

async function adminLogin(request, env, nowSeconds) {
  const body = await readJsonBody(request);
  const username = typeof body.username === "string" ? body.username.trim() : "";
  const password = typeof body.password === "string" ? body.password : "";
  const db = requireDatabase(env);
  const scopeHash = await rateLimitScope(request, username);
  await checkLoginRateLimit(db, scopeHash, nowSeconds);
  const admin = await db
    .prepare(
      `SELECT user_id, username, display_name, password_hash
       FROM users
       WHERE username = ? COLLATE NOCASE
         AND role = 'admin'
         AND is_active = 1
       LIMIT 1`,
    )
    .bind(username)
    .first();
  if (!admin || !(await verifyPassword(password, admin.password_hash))) {
    await recordLoginFailure(db, scopeHash, nowSeconds);
    throw new ApiError("Username atau kata sandi administrator tidak valid.", 401);
  }
  await clearLoginFailures(db, scopeHash);

  const token = randomToken();
  const timestamp = nowSeconds();
  const expiresAt = timestamp + ADMIN_SESSION_SECONDS;
  await db
    .prepare(
      "INSERT INTO admin_sessions (token_hash, user_id, expires_at, created_at) VALUES (?, ?, ?, ?)",
    )
    .bind(await digestHex(token), admin.user_id, expiresAt, timestamp)
    .run();
  await db
    .prepare("DELETE FROM admin_sessions WHERE expires_at <= ?")
    .bind(timestamp)
    .run();
  return {
    token,
    expires_at: expiresAt,
    username: admin.username,
    display_name: admin.display_name,
  };
}

async function operatorLogin(request, env, nowSeconds) {
  const body = await readJsonBody(request);
  const username = typeof body.username === "string" ? body.username.trim() : "";
  const password = typeof body.password === "string" ? body.password : "";
  const db = requireDatabase(env);
  const scopeHash = await rateLimitScope(request, username);
  await checkLoginRateLimit(db, scopeHash, nowSeconds);
  const user = await db
    .prepare(
      `SELECT display_name, password_hash
       FROM users
       WHERE username = ? COLLATE NOCASE
         AND role = 'operator'
         AND is_active = 1
       LIMIT 1`,
    )
    .bind(username)
    .first();
  const valid = user
    ? await verifyPassword(password, user.password_hash)
    : (await hashPassword(password || "dummy-credential-value"), false);
  if (!valid || !user) {
    await recordLoginFailure(db, scopeHash, nowSeconds);
    throw new ApiError("Username atau kata sandi tidak valid.", 401);
  }
  await clearLoginFailures(db, scopeHash);
  return { authenticated: true, display_name: user.display_name };
}

async function adminStatus(env) {
  const count = await requireDatabase(env)
    .prepare("SELECT COUNT(*) AS admin_count FROM users WHERE role = 'admin'")
    .first();
  return { bootstrap_required: Number(count?.admin_count || 0) === 0 };
}

async function listAdminUsers(request, env, nowSeconds) {
  await getAdminFromSession(request, env, nowSeconds);
  const result = await requireDatabase(env)
    .prepare(
      `SELECT username, display_name, role, is_active, created_at, updated_at
       FROM users ORDER BY role, username`,
    )
    .all();
  return { users: result.results || [] };
}

async function createAdminUser(request, env, nowSeconds) {
  await getAdminFromSession(request, env, nowSeconds);
  const body = await readJsonBody(request);
  const username = typeof body.username === "string" ? body.username.trim() : "";
  const displayName =
    typeof body.display_name === "string" ? body.display_name.trim() : "";
  const role = body.role === "admin" ? "admin" : "operator";
  if (!/^[A-Za-z0-9_.-]{3,64}$/.test(username) || !displayName || displayName.length > 100) {
    throw new ApiError("Username atau nama pengguna tidak valid.");
  }
  const passwordHash = await hashPassword(body.password);
  const timestamp = nowSeconds();
  try {
    await requireDatabase(env)
      .prepare(
        `INSERT INTO users
          (user_id, username, display_name, password_hash, role, is_active, created_at, updated_at)
         VALUES (?, ?, ?, ?, ?, 1, ?, ?)`,
      )
      .bind(crypto.randomUUID(), username, displayName, passwordHash, role, timestamp, timestamp)
      .run();
  } catch (error) {
    if (/unique|constraint/i.test(String(error))) {
      throw new ApiError("Username tersebut sudah digunakan.", 409);
    }
    throw error;
  }
  return { created: true };
}

async function resetAdminUserPassword(request, env, nowSeconds) {
  await getAdminFromSession(request, env, nowSeconds);
  const body = await readJsonBody(request);
  const username = typeof body.username === "string" ? body.username.trim() : "";
  if (!username) throw new ApiError("Username tidak valid.");
  const passwordHash = await hashPassword(body.password);
  const result = await requireDatabase(env)
    .prepare(
      "UPDATE users SET password_hash = ?, updated_at = ? WHERE username = ? COLLATE NOCASE",
    )
    .bind(passwordHash, nowSeconds(), username)
    .run();
  if (result.meta?.changes !== 1) throw new ApiError("Akun tidak ditemukan.", 404);
  return { updated: true };
}

async function setAdminUserActive(request, env, nowSeconds) {
  const admin = await getAdminFromSession(request, env, nowSeconds);
  const body = await readJsonBody(request);
  const username = typeof body.username === "string" ? body.username.trim() : "";
  if (typeof body.active !== "boolean" || !username) {
    throw new ApiError("Status akun tidak valid.");
  }
  if (!body.active && username.toLowerCase() === admin.username.toLowerCase()) {
    throw new ApiError("Administrator tidak dapat menonaktifkan akunnya sendiri.");
  }
  const db = requireDatabase(env);
  const result = await db
    .prepare(
      `UPDATE users SET is_active = ?, updated_at = ?
       WHERE username = ? COLLATE NOCASE AND role = 'operator'`,
    )
    .bind(body.active ? 1 : 0, nowSeconds(), username)
    .run();
  if (result.meta?.changes !== 1) throw new ApiError("Akun operator tidak ditemukan.", 404);
  return { updated: true };
}

async function issueAdminLicense(request, env, publicKeyHex, nowSeconds) {
  await getAdminFromSession(request, env, nowSeconds);
  const body = await readJsonBody(request);
  let email;
  try {
    email = normalizeEmail(body.email);
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError("Alamat email tidak valid.");
  }
  const machineId =
    typeof body.machine_id === "string" ? body.machine_id.trim().toUpperCase() : "";
  const days = body.days;
  const operator =
    typeof body.operator === "string" ? body.operator.trim() : "NOC_Operator";
  if (
    !machineId ||
    machineId.length > 128 ||
    !Number.isSafeInteger(days) ||
    days < 1 ||
    days > 3650 ||
    !operator ||
    operator.length > 100
  ) {
    throw new ApiError("Data lisensi tidak valid.");
  }
  const signingKey = await importSigningKey(
    env.LICENSE_SIGNING_PRIVATE_KEY,
    publicKeyHex,
  );
  const issuedAt = nowSeconds();
  const licenseId = randomToken(24);
  const licenseType = days === 30 ? "1_MONTH" : `${days}_DAYS`;
  const payload = {
    v: 3,
    email,
    mid: machineId,
    days,
    jti: licenseId,
    iat: issuedAt,
    type: licenseType,
    op: operator,
  };
  const payloadBytes = encoder.encode(JSON.stringify(payload));
  const signature = new Uint8Array(
    await crypto.subtle.sign("Ed25519", signingKey, payloadBytes),
  );
  const signedBlob = new Uint8Array(payloadBytes.length + signature.length);
  signedBlob.set(payloadBytes);
  signedBlob.set(signature, payloadBytes.length);
  const licenseKey = `${LICENSE_PREFIX}${bytesToBase64Url(signedBlob)}`;
  await requireDatabase(env)
    .prepare(
      `INSERT INTO license_issues
        (license_id, email, machine_id, days_valid, license_type, operator, issued_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`,
    )
    .bind(licenseId, email, machineId, days, licenseType, operator, issuedAt)
    .run();
  return { license_key: licenseKey, email, machine_id: machineId, days, issued_at: issuedAt };
}

async function listAdminLicenses(request, env, nowSeconds) {
  await getAdminFromSession(request, env, nowSeconds);
  const result = await requireDatabase(env)
    .prepare(
      `SELECT license_issues.license_id, license_issues.email,
              license_issues.machine_id, license_issues.days_valid,
              license_issues.license_type, license_issues.operator,
              license_issues.issued_at, license_activation_history.activated_at,
              license_activation_history.expires_at,
              CASE
                WHEN license_activation_history.license_id IS NULL THEN 'not_activated'
                WHEN license_activation_history.expires_at <= ? THEN 'expired'
                ELSE 'active'
              END AS status
       FROM license_issues
       LEFT JOIN license_activation_history
         ON license_activation_history.license_id = license_issues.license_id
       ORDER BY license_issues.issued_at DESC LIMIT 200`,
    )
    .bind(nowSeconds())
    .all();
  return { licenses: result.results || [] };
}

async function deleteExpiredAdminLicenses(request, env, nowSeconds) {
  await getAdminFromSession(request, env, nowSeconds);
  const timestamp = nowSeconds();
  const results = await requireDatabase(env).batch([
    requireDatabase(env)
      .prepare(
        `DELETE FROM license_issues
         WHERE license_id IN (
           SELECT license_id
           FROM license_activation_history
           WHERE expires_at <= ?
         )`,
      )
      .bind(timestamp),
    requireDatabase(env)
      .prepare("DELETE FROM license_activations WHERE expires_at <= ?")
      .bind(timestamp),
  ]);
  return {
    deleted_licenses: results[0]?.meta?.changes || 0,
    cleared_activations: results[1]?.meta?.changes || 0,
  };
}

async function adminLogout(request, env) {
  const authorization = request.headers.get("Authorization") || "";
  const match = /^Bearer ([A-Za-z0-9_-]{40,128})$/.exec(authorization);
  if (match) {
    await requireDatabase(env)
      .prepare("DELETE FROM admin_sessions WHERE token_hash = ?")
      .bind(await digestHex(match[1]))
      .run();
  }
  return { logged_out: true };
}

async function activate(request, env, { publicKeyHex, nowSeconds }) {
  if (!env.DB || typeof env.DB.prepare !== "function" || typeof env.DB.batch !== "function") {
    throw new ApiError("Database aktivasi tidak tersedia.", 503);
  }

  const body = await readJsonBody(request);
  let email;
  try {
    email = normalizeEmail(body.email);
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError("Alamat email tidak valid.");
  }
  if (typeof body.license_key !== "string" || body.license_key.length > 8192) {
    throw new ApiError("Format token lisensi tidak didukung.");
  }
  if (typeof body.machine_id !== "string") {
    throw new ApiError("Machine ID tidak valid.");
  }
  const machineId = body.machine_id.trim().toUpperCase();
  if (!machineId || machineId.length > 128) {
    throw new ApiError("Machine ID tidak valid.");
  }

  const payload = await decodeIssuedLicense(body.license_key.trim(), publicKeyHex);
  const days = payload.days;
  const issuedAt = payload.iat;
  const licenseId = payload.jti;
  const payloadEmail = payload.email;
  const payloadMachineId = payload.mid;
  const licenseType = payload.type;
  const operator = payload.op;
  if (
    payload.v !== 3 ||
    !Number.isSafeInteger(days) ||
    days <= 0 ||
    !Number.isSafeInteger(issuedAt) ||
    issuedAt < 0 ||
    typeof licenseId !== "string" ||
    !licenseId ||
    typeof payloadEmail !== "string" ||
    typeof payloadMachineId !== "string" ||
    typeof licenseType !== "string" ||
    !licenseType ||
    typeof operator !== "string"
  ) {
    throw new ApiError("Payload lisensi tidak valid.");
  }
  if (normalizeEmail(payloadEmail) !== email) {
    throw new ApiError("Email tidak cocok dengan lisensi yang diterbitkan.");
  }
  if (payloadMachineId.trim().toUpperCase() !== machineId) {
    throw new ApiError("Lisensi ini terikat ke perangkat lain.");
  }

  const currentTime = nowSeconds();
  if (!Number.isSafeInteger(currentTime) || issuedAt > currentTime + 300) {
    throw new ApiError("Waktu penerbitan lisensi tidak valid.");
  }
  const expiresAt = currentTime + days * 86400;
  if (!Number.isSafeInteger(expiresAt)) {
    throw new ApiError("Durasi lisensi tidak valid.");
  }

  const signingKey = await importSigningKey(
    env.LICENSE_SIGNING_PRIVATE_KEY,
    publicKeyHex,
  );
  const activationToken = await signActivation(
    {
      v: 1,
      kind: "activation",
      email,
      mid: machineId,
      jti: licenseId,
      iat: currentTime,
      exp: expiresAt,
      type: licenseType,
      op: operator,
      nonce: randomToken(18),
    },
    signingKey,
  );

  const results = await env.DB.batch([
    env.DB.prepare(
      `INSERT OR IGNORE INTO license_activation_history
        (license_id, email, machine_id, activated_at, expires_at, activation_token)
       SELECT ?, ?, ?, ?, ?, ?
       WHERE NOT EXISTS (
         SELECT 1 FROM license_activations
         WHERE email = ? COLLATE NOCASE AND machine_id != ?
       )`,
    ).bind(
      licenseId,
      email,
      machineId,
      currentTime,
      expiresAt,
      activationToken,
      email,
      machineId,
    ),
    env.DB.prepare(
      `INSERT INTO license_activations
        (email, license_id, machine_id, activated_at, expires_at, activation_token)
       SELECT email, license_id, machine_id, activated_at, expires_at, activation_token
       FROM license_activation_history
       WHERE license_id = ? AND activation_token = ?
       ON CONFLICT(email) DO UPDATE SET
         license_id = excluded.license_id,
         machine_id = excluded.machine_id,
         activated_at = excluded.activated_at,
         expires_at = excluded.expires_at,
         activation_token = excluded.activation_token
       WHERE license_activations.machine_id = excluded.machine_id
         AND license_activations.license_id != excluded.license_id`,
    ).bind(licenseId, activationToken),
    env.DB.prepare(
      `SELECT email, license_id, machine_id, activation_token
       FROM license_activation_history
       WHERE license_id = ?
       LIMIT 1`,
    ).bind(licenseId),
    env.DB.prepare(
      `SELECT email, license_id, machine_id, activation_token
       FROM license_activations
       WHERE email = ?
       LIMIT 1`,
    ).bind(email),
  ]);

  const history = results[2]?.results?.[0];
  const current = results[3]?.results?.[0];
  if (!history) {
    if (current && current.machine_id !== machineId) {
      throw new ApiError("Email ini sudah terikat ke perangkat lain.", 409);
    }
    throw new ApiError("Catatan aktivasi tidak dapat dibaca.", 503);
  }
  if (
    history.email.toLowerCase() !== email ||
    history.machine_id !== machineId
  ) {
    throw new ApiError("License key ini sudah pernah digunakan.", 409);
  }
  if (current && current.machine_id !== machineId) {
    throw new ApiError("Email ini sudah terikat ke perangkat lain.", 409);
  }
  if (!current) {
    throw new ApiError("Catatan aktivasi tidak dapat dibaca.", 503);
  }
  if (current.license_id !== licenseId) {
    throw new ApiError(
      "Lisensi ini sudah digantikan oleh aktivasi yang lebih baru.",
      409,
    );
  }

  return { activation_token: history.activation_token };
}

export async function handleRequest(
  request,
  env,
  {
    publicKeyHex = LICENSE_PUBLIC_KEY_HEX,
    nowSeconds = () => Math.floor(Date.now() / 1000),
  } = {},
) {
  const url = new URL(request.url);
  if (url.protocol !== "https:") {
    return jsonResponse({ detail: "Layanan aktivasi harus diakses melalui HTTPS." }, 400);
  }
  if (url.pathname === "/health" && request.method === "GET") {
    return jsonResponse({ status: "ok" });
  }

  try {
    let result;
    const path = url.pathname;
    const method = request.method;
    if (path === "/v1/activate" && method === "POST") {
      result = await activate(request, env, { publicKeyHex, nowSeconds });
    } else if (path === "/v1/login" && method === "POST") {
      result = await operatorLogin(request, env, nowSeconds);
    } else if (path === "/v1/admin/status" && method === "GET") {
      result = await adminStatus(env);
    } else if (path === "/v1/admin/bootstrap" && method === "POST") {
      result = await adminBootstrap(request, env, nowSeconds);
    } else if (path === "/v1/admin/login" && method === "POST") {
      result = await adminLogin(request, env, nowSeconds);
    } else if (path === "/v1/admin/logout" && method === "POST") {
      result = await adminLogout(request, env);
    } else if (path === "/v1/admin/users" && method === "GET") {
      result = await listAdminUsers(request, env, nowSeconds);
    } else if (path === "/v1/admin/users" && method === "POST") {
      result = await createAdminUser(request, env, nowSeconds);
    } else if (path === "/v1/admin/users/password" && method === "POST") {
      result = await resetAdminUserPassword(request, env, nowSeconds);
    } else if (path === "/v1/admin/users/status" && method === "POST") {
      result = await setAdminUserActive(request, env, nowSeconds);
    } else if (path === "/v1/admin/licenses/issue" && method === "POST") {
      result = await issueAdminLicense(request, env, publicKeyHex, nowSeconds);
    } else if (path === "/v1/admin/licenses" && method === "GET") {
      result = await listAdminLicenses(request, env, nowSeconds);
    } else if (
      path === "/v1/admin/licenses/expired" &&
      method === "DELETE"
    ) {
      result = await deleteExpiredAdminLicenses(request, env, nowSeconds);
    } else if (
      path === "/v1/activate" ||
      path === "/v1/login" ||
      path.startsWith("/v1/admin/")
    ) {
      return jsonResponse({ detail: "Method tidak diizinkan." }, 405);
    } else {
      return jsonResponse({ detail: "Endpoint tidak ditemukan." }, 404);
    }
    return jsonResponse(result);
  } catch (error) {
    if (error instanceof ApiError) {
      return jsonResponse({ detail: error.message }, error.status);
    }
    console.error("License activation service failed.", error);
    return jsonResponse(
      { detail: "Layanan aktivasi mengalami gangguan; hubungi administrator." },
      503,
    );
  }
}

export default {
  fetch(request, env) {
    return handleRequest(request, env);
  },
};
