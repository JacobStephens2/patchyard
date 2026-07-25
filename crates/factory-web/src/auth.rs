//! Cookie, CSRF, and request-authentication helpers.

use std::time::Duration;

use axum::http::{HeaderMap, header};
use base64::{Engine as _, engine::general_purpose::URL_SAFE_NO_PAD};
use factory_core::auth::hash_password;
use sha2::{Digest as _, Sha256};
use thiserror::Error;
use time::OffsetDateTime;
use uuid::Uuid;

use crate::store::{DashboardStore, Principal, SESSION_ABSOLUTE, StoreError};

pub const SESSION_COOKIE: &str = "__Host-patchyard_session";
pub const LOGIN_COOKIE: &str = "__Host-patchyard_login";

#[derive(Clone, Debug)]
pub struct Authenticated {
    pub principal: Principal,
    pub token_hash: [u8; 32],
    pub csrf_token: String,
}

#[derive(Clone, Debug)]
pub struct Secret {
    pub value: String,
    pub hash: [u8; 32],
}

#[must_use]
pub fn new_secret() -> Secret {
    let mut bytes = [0_u8; 32];
    bytes[..16].copy_from_slice(Uuid::new_v4().as_bytes());
    bytes[16..].copy_from_slice(Uuid::new_v4().as_bytes());
    let value = URL_SAFE_NO_PAD.encode(bytes);
    Secret {
        hash: hash_secret(&value),
        value,
    }
}

#[must_use]
pub fn csrf_for_secret(secret: &str) -> Secret {
    let mut hasher = Sha256::new();
    hasher.update(b"patchyard-csrf-v1\0");
    hasher.update(secret.as_bytes());
    let bytes: [u8; 32] = hasher.finalize().into();
    let value = URL_SAFE_NO_PAD.encode(bytes);
    Secret {
        hash: hash_secret(&value),
        value,
    }
}

#[must_use]
pub fn hash_secret(value: &str) -> [u8; 32] {
    Sha256::digest(value.as_bytes()).into()
}

pub async fn authenticate(
    store: &DashboardStore,
    headers: &HeaderMap,
) -> Result<Option<Authenticated>, AuthError> {
    let Some(raw_token) = cookie(headers, SESSION_COOKIE) else {
        return Ok(None);
    };
    if !valid_encoded_secret(&raw_token) {
        return Ok(None);
    }
    let token_hash = hash_secret(&raw_token);
    let Some(principal) = store.authenticate(&token_hash).await? else {
        return Ok(None);
    };
    let csrf = csrf_for_secret(&raw_token);
    if csrf.hash != principal.csrf_hash {
        return Err(AuthError::SessionCsrfMismatch);
    }
    Ok(Some(Authenticated {
        principal,
        token_hash,
        csrf_token: csrf.value,
    }))
}

#[must_use]
pub fn csrf_valid(authenticated: &Authenticated, submitted: &str) -> bool {
    !submitted.is_empty() && hash_secret(submitted) == authenticated.principal.csrf_hash
}

#[must_use]
pub fn login_challenge_valid(raw_cookie: &str, submitted: &str) -> Option<([u8; 32], [u8; 32])> {
    if !valid_encoded_secret(raw_cookie) || submitted.is_empty() {
        return None;
    }
    let expected = csrf_for_secret(raw_cookie);
    (hash_secret(submitted) == expected.hash).then(|| (hash_secret(raw_cookie), expected.hash))
}

#[must_use]
pub fn session_cookie(secret: &str, _absolute_expires_at: OffsetDateTime) -> String {
    secure_cookie(SESSION_COOKIE, secret, SESSION_ABSOLUTE, "/")
}

#[must_use]
pub fn login_cookie(secret: &str, lifetime: Duration) -> String {
    // `__Host-` cookies are valid only with Path=/ (RFC 6265bis). Browsers
    // reject a narrower path before the login POST can prove its CSRF token.
    secure_cookie(LOGIN_COOKIE, secret, lifetime, "/")
}

#[must_use]
pub fn clear_session_cookie() -> String {
    clear_cookie(SESSION_COOKIE, "/")
}

#[must_use]
pub fn clear_login_cookie() -> String {
    clear_cookie(LOGIN_COOKIE, "/")
}

#[must_use]
pub fn cookie(headers: &HeaderMap, name: &str) -> Option<String> {
    headers
        .get_all(header::COOKIE)
        .iter()
        .filter_map(|value| value.to_str().ok())
        .flat_map(|value| value.split(';'))
        .filter_map(|pair| pair.trim().split_once('='))
        .find_map(|(candidate, value)| (candidate == name).then(|| value.to_owned()))
}

#[must_use]
pub fn client_key(headers: &HeaderMap) -> String {
    headers
        .get("x-forwarded-for")
        .and_then(|value| value.to_str().ok())
        .and_then(|value| value.split(',').next())
        .map(str::trim)
        .filter(|value| {
            !value.is_empty()
                && value.len() <= 64
                && value
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit() || matches!(byte, b'.' | b':'))
        })
        .unwrap_or("unix-local")
        .to_owned()
}

/// Build the fixed-cost dummy PHC value once at startup.
///
/// The login handler verifies against this value for unknown accounts so
/// account discovery does not bypass the same Argon2 work factor.
pub fn dummy_password_hash() -> Result<String, factory_core::auth::AuthError> {
    hash_password("patchyard-dummy-password-never-used")
}

fn valid_encoded_secret(value: &str) -> bool {
    value.len() == 43
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

fn secure_cookie(name: &str, value: &str, lifetime: Duration, path: &str) -> String {
    format!(
        "{name}={value}; Path={path}; Max-Age={}; Secure; HttpOnly; SameSite=Strict",
        lifetime.as_secs()
    )
}

fn clear_cookie(name: &str, path: &str) -> String {
    format!("{name}=; Path={path}; Max-Age=0; Secure; HttpOnly; SameSite=Strict")
}

#[derive(Debug, Error)]
pub enum AuthError {
    #[error("dashboard auth store failed: {0}")]
    Store(#[from] StoreError),
    #[error("session CSRF state is inconsistent")]
    SessionCsrfMismatch,
}

#[cfg(test)]
mod tests {
    use std::time::Duration;

    use axum::http::{HeaderMap, HeaderValue, header};

    use super::{
        LOGIN_COOKIE, SESSION_COOKIE, clear_login_cookie, client_key, cookie, csrf_for_secret,
        login_cookie, new_secret, session_cookie,
    };

    #[test]
    fn cookies_are_host_only_secure_and_strict() {
        let secret = new_secret();
        let cookie = session_cookie(&secret.value, time::OffsetDateTime::now_utc());
        assert!(cookie.starts_with(&format!("{SESSION_COOKIE}=")));
        assert!(cookie.contains("; Path=/;"));
        assert!(cookie.contains("; Secure; HttpOnly; SameSite=Strict"));
        assert!(!cookie.contains("Domain="));
    }

    #[test]
    fn host_prefixed_login_cookie_is_root_scoped_when_issued_and_cleared() {
        let secret = new_secret();
        let issued = login_cookie(&secret.value, Duration::from_secs(600));
        let cleared = clear_login_cookie();

        for cookie in [issued, cleared] {
            assert!(cookie.starts_with(&format!("{LOGIN_COOKIE}=")));
            assert!(cookie.contains("; Path=/;"));
            assert!(!cookie.contains("Path=/login"));
            assert!(!cookie.contains("Domain="));
        }
    }

    #[test]
    fn cookie_parser_and_csrf_derivation_are_stable() {
        let secret = new_secret();
        let mut headers = HeaderMap::new();
        headers.insert(
            header::COOKIE,
            HeaderValue::from_str(&format!(
                "unrelated=x; {LOGIN_COOKIE}={}; more=y",
                secret.value
            ))
            .expect("header"),
        );
        assert_eq!(
            cookie(&headers, LOGIN_COOKIE).as_deref(),
            Some(secret.value.as_str())
        );
        assert_eq!(
            csrf_for_secret(&secret.value).value,
            csrf_for_secret(&secret.value).value
        );
    }

    #[test]
    fn forwarded_client_key_is_bounded_and_syntax_checked() {
        let mut headers = HeaderMap::new();
        headers.insert(
            "x-forwarded-for",
            HeaderValue::from_static("192.0.2.4, 10.0.0.1"),
        );
        assert_eq!(client_key(&headers), "192.0.2.4");
        headers.insert(
            "x-forwarded-for",
            HeaderValue::from_static("attacker.example"),
        );
        assert_eq!(client_key(&headers), "unix-local");
    }
}
