//! Shared domain types and constants for Patchyard Factory.

use std::{error::Error, fmt};

pub mod auth;
pub mod plan;
pub mod schema;
pub mod state;
pub mod triage;

/// HTML `maxlength` and server-side request-body limit, measured in UTF-16
/// code units as required by the HTML specification.
pub const REQUEST_BODY_MAX_UTF16_CODE_UNITS: usize = 20_000;

/// Whether the dashboard's HTML request-body field carries `required`.
pub const REQUEST_BODY_HTML_REQUIRED: bool = true;

/// A request body that passed the single intake quality gate.
///
/// The inner text is deliberately private so every caller enters through
/// [`RequestBody::parse`]. This gate rejects missing or impractically large
/// input; it is not a security boundary and preserves accepted input verbatim.
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RequestBody(String);

impl RequestBody {
    /// Parse one request body without normalizing or interpreting its content.
    ///
    /// # Errors
    ///
    /// Returns [`RequestBodyError::Empty`] for empty or all-whitespace input,
    /// and [`RequestBodyError::TooLong`] when the HTML-compatible limit is
    /// exceeded.
    pub fn parse(input: impl Into<String>) -> Result<Self, RequestBodyError> {
        let input = input.into();
        if input.trim().is_empty() {
            return Err(RequestBodyError::Empty);
        }

        let actual = input.encode_utf16().count();
        if actual > REQUEST_BODY_MAX_UTF16_CODE_UNITS {
            return Err(RequestBodyError::TooLong {
                actual,
                maximum: REQUEST_BODY_MAX_UTF16_CODE_UNITS,
            });
        }

        Ok(Self(input))
    }

    /// Borrow the verbatim request body.
    #[must_use]
    pub fn as_str(&self) -> &str {
        &self.0
    }

    /// Return the owned, verbatim request body.
    #[must_use]
    pub fn into_string(self) -> String {
        self.0
    }
}

/// Why intake parsing rejected a request body.
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RequestBodyError {
    /// The body was empty or contained only whitespace.
    Empty,
    /// The body exceeded the shared HTML/server limit.
    TooLong {
        /// Observed length in UTF-16 code units.
        actual: usize,
        /// Allowed length in UTF-16 code units.
        maximum: usize,
    },
}

impl fmt::Display for RequestBodyError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Empty => formatter.write_str("request body must not be blank"),
            Self::TooLong { actual, maximum } => write!(
                formatter,
                "request body is {actual} UTF-16 code units; maximum is {maximum}"
            ),
        }
    }
}

impl Error for RequestBodyError {}

#[cfg(test)]
mod tests {
    use super::{REQUEST_BODY_MAX_UTF16_CODE_UNITS, RequestBody, RequestBodyError};

    #[test]
    fn accepted_text_is_preserved_verbatim() {
        let input = "  Keep this whitespace.\r\nAnd this line.  ";

        let parsed = RequestBody::parse(input).expect("nonblank request should parse");

        assert_eq!(parsed.as_str(), input);
        assert_eq!(parsed.into_string(), input);
    }

    #[test]
    fn empty_and_whitespace_only_text_are_rejected() {
        assert_eq!(RequestBody::parse(""), Err(RequestBodyError::Empty));
        assert_eq!(RequestBody::parse(" \t\r\n"), Err(RequestBodyError::Empty));
    }

    #[test]
    fn exact_limit_is_accepted_and_one_more_is_rejected() {
        let at_limit = "a".repeat(REQUEST_BODY_MAX_UTF16_CODE_UNITS);
        let over_limit = "a".repeat(REQUEST_BODY_MAX_UTF16_CODE_UNITS + 1);

        assert!(RequestBody::parse(at_limit).is_ok());
        assert_eq!(
            RequestBody::parse(over_limit),
            Err(RequestBodyError::TooLong {
                actual: REQUEST_BODY_MAX_UTF16_CODE_UNITS + 1,
                maximum: REQUEST_BODY_MAX_UTF16_CODE_UNITS,
            })
        );
    }

    #[test]
    fn limit_uses_html_compatible_utf16_code_units() {
        let input = format!(
            "{}\u{1f680}",
            "a".repeat(REQUEST_BODY_MAX_UTF16_CODE_UNITS - 1)
        );

        assert_eq!(
            RequestBody::parse(input),
            Err(RequestBodyError::TooLong {
                actual: REQUEST_BODY_MAX_UTF16_CODE_UNITS + 1,
                maximum: REQUEST_BODY_MAX_UTF16_CODE_UNITS,
            })
        );
    }
}
