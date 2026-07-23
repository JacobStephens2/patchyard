//! Factory-native account primitives shared by bootstrap tooling and the web
//! service. Database authorization remains in each caller's narrow repository.

use argon2::{
    Argon2, PasswordHash, PasswordHasher as _, PasswordVerifier as _,
    password_hash::{SaltString, rand_core::OsRng},
};
use thiserror::Error;

/// Minimum operator-provisioned password length.
pub const PASSWORD_MIN_CHARACTERS: usize = 14;
/// Defensive upper bound before running the intentionally expensive KDF.
pub const PASSWORD_MAX_BYTES: usize = 1_024;
/// HTML `maxlength` for login identifiers.
pub const USERNAME_MAX_BYTES: usize = 254;

/// Authorization values stored in factory PostgreSQL, never in orchestration.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AccountRole {
    Submitter,
    Admin,
}

impl AccountRole {
    #[must_use]
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Submitter => "factory_submit",
            Self::Admin => "factory_admin",
        }
    }

    pub fn parse(value: &str) -> Result<Self, AuthError> {
        match value {
            "factory_submit" => Ok(Self::Submitter),
            "factory_admin" => Ok(Self::Admin),
            _ => Err(AuthError::InvalidRole),
        }
    }

    #[must_use]
    pub const fn can_admin(self) -> bool {
        matches!(self, Self::Admin)
    }

    #[must_use]
    pub const fn can_submit(self) -> bool {
        matches!(self, Self::Submitter | Self::Admin)
    }
}

/// Normalize the login identifier once so lookup and uniqueness agree.
pub fn normalize_username(value: &str) -> Result<String, AuthError> {
    let normalized = value.trim().to_ascii_lowercase();
    if normalized.is_empty()
        || normalized.len() > USERNAME_MAX_BYTES
        || !normalized.is_ascii()
        || normalized
            .bytes()
            .any(|byte| byte.is_ascii_control() || byte.is_ascii_whitespace())
    {
        return Err(AuthError::InvalidUsername);
    }
    Ok(normalized)
}

/// Hash one operator-supplied password with Argon2id and a fresh salt.
///
/// This is CPU-bound by design. Async callers must invoke it through
/// `spawn_blocking`; synchronous bootstrap commands may call it directly.
pub fn hash_password(password: &str) -> Result<String, AuthError> {
    validate_new_password(password)?;
    let salt = SaltString::generate(&mut OsRng);
    Ok(Argon2::default()
        .hash_password(password.as_bytes(), &salt)?
        .to_string())
}

/// Verify a password against a PHC string.
///
/// This is CPU-bound by design. Async callers must invoke it through
/// `spawn_blocking`.
pub fn verify_password(password: &str, encoded: &str) -> bool {
    if password.len() > PASSWORD_MAX_BYTES {
        return false;
    }
    let Ok(hash) = PasswordHash::new(encoded) else {
        return false;
    };
    Argon2::default()
        .verify_password(password.as_bytes(), &hash)
        .is_ok()
}

fn validate_new_password(password: &str) -> Result<(), AuthError> {
    if password.chars().count() < PASSWORD_MIN_CHARACTERS {
        return Err(AuthError::PasswordTooShort);
    }
    if password.len() > PASSWORD_MAX_BYTES {
        return Err(AuthError::PasswordTooLong);
    }
    Ok(())
}

#[derive(Debug, Error)]
pub enum AuthError {
    #[error("username is invalid")]
    InvalidUsername,
    #[error("account role is invalid")]
    InvalidRole,
    #[error("password must contain at least {PASSWORD_MIN_CHARACTERS} characters")]
    PasswordTooShort,
    #[error("password exceeds {PASSWORD_MAX_BYTES} bytes")]
    PasswordTooLong,
    #[error("password hashing failed: {0}")]
    PasswordHash(#[from] argon2::password_hash::Error),
}

#[cfg(test)]
mod tests {
    use super::{
        AccountRole, PASSWORD_MIN_CHARACTERS, hash_password, normalize_username, verify_password,
    };

    #[test]
    fn usernames_are_canonical_ascii_identifiers() {
        assert_eq!(
            normalize_username(" Jacob@example.com ").expect("valid"),
            "jacob@example.com"
        );
        assert!(normalize_username("two words").is_err());
        assert!(normalize_username("josé@example.com").is_err());
    }

    #[test]
    fn argon2_hashes_are_salted_and_verify() {
        let password = "x".repeat(PASSWORD_MIN_CHARACTERS);
        let first = hash_password(&password).expect("hash");
        let second = hash_password(&password).expect("hash");
        assert_ne!(first, second);
        assert!(first.starts_with("$argon2id$"));
        assert!(verify_password(&password, &first));
        assert!(!verify_password("incorrect-password", &first));
    }

    #[test]
    fn roles_are_database_native() {
        assert!(AccountRole::Admin.can_admin());
        assert!(AccountRole::Admin.can_submit());
        assert!(!AccountRole::Submitter.can_admin());
        assert_eq!(AccountRole::Submitter.as_str(), "factory_submit");
    }
}
