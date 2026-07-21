//! One PostgreSQL catalog implementation shared by the committed ERD and the
//! later authenticated `/schema` projection.

use std::{collections::BTreeMap, fmt::Write as _};

use serde::Serialize;
use sqlx::{AssertSqlSafe, PgPool, Row};
use thiserror::Error;

/// Complete state-schema catalog needed by both projections.
#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct SchemaCatalog {
    pub relations: Vec<Relation>,
    pub foreign_keys: Vec<ForeignKey>,
    pub indexes: Vec<Index>,
    pub grants: Vec<GrantScope>,
    pub roles: Vec<RoleScope>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct Relation {
    pub name: String,
    pub kind: String,
    pub row_count: i64,
    pub columns: Vec<Column>,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct Column {
    pub name: String,
    pub data_type: String,
    pub nullable: bool,
    pub primary_key: bool,
    pub unique: bool,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct ForeignKey {
    pub name: String,
    pub source_relation: String,
    pub source_column: String,
    pub target_relation: String,
    pub target_column: String,
    pub source_nullable: bool,
    pub source_unique: bool,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct Index {
    pub relation: String,
    pub name: String,
    pub primary: bool,
    pub unique: bool,
    pub definition: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct GrantScope {
    pub grantee: String,
    pub relation: String,
    pub column: Option<String>,
    pub privilege: String,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize)]
pub struct RoleScope {
    pub name: String,
    pub can_login: bool,
    pub superuser: bool,
    pub create_db: bool,
    pub create_role: bool,
}

/// Read tables, columns, indexes, FKs/cardinality, roles/grants, and counts.
pub async fn introspect(pool: &PgPool) -> Result<SchemaCatalog, SchemaError> {
    let column_rows = sqlx::query(
        r#"
        SELECT
            relation.relname AS relation_name,
            relation.relkind::text AS relation_kind,
            attribute.attname AS column_name,
            pg_catalog.format_type(attribute.atttypid, attribute.atttypmod) AS data_type,
            NOT attribute.attnotnull AS nullable,
            EXISTS (
                SELECT 1
                FROM pg_catalog.pg_index primary_index
                WHERE primary_index.indrelid = relation.oid
                  AND primary_index.indisprimary
                  AND attribute.attnum = ANY(primary_index.indkey)
            ) AS primary_key,
            EXISTS (
                SELECT 1
                FROM pg_catalog.pg_index unique_index
                WHERE unique_index.indrelid = relation.oid
                  AND unique_index.indisunique
                  AND unique_index.indnatts = 1
                  AND attribute.attnum = ANY(unique_index.indkey)
            ) AS unique_column
        FROM pg_catalog.pg_class relation
        JOIN pg_catalog.pg_namespace namespace ON namespace.oid = relation.relnamespace
        JOIN pg_catalog.pg_attribute attribute ON attribute.attrelid = relation.oid
        WHERE namespace.nspname = 'factory'
          AND relation.relkind IN ('r', 'v')
          AND attribute.attnum > 0
          AND NOT attribute.attisdropped
        ORDER BY relation.relname, attribute.attnum
        "#,
    )
    .fetch_all(pool)
    .await?;

    let mut relations: BTreeMap<String, Relation> = BTreeMap::new();
    for row in column_rows {
        let relation_name: String = row.try_get("relation_name")?;
        let relation_kind: String = row.try_get("relation_kind")?;
        let relation = relations
            .entry(relation_name.clone())
            .or_insert_with(|| Relation {
                name: relation_name,
                kind: if relation_kind == "r" {
                    "table"
                } else {
                    "view"
                }
                .to_owned(),
                row_count: 0,
                columns: Vec::new(),
            });
        relation.columns.push(Column {
            name: row.try_get("column_name")?,
            data_type: row.try_get("data_type")?,
            nullable: row.try_get("nullable")?,
            primary_key: row.try_get("primary_key")?,
            unique: row.try_get("unique_column")?,
        });
    }

    for relation in relations.values_mut() {
        let query = format!(
            "SELECT count(*)::bigint AS row_count FROM factory.{}",
            quote_identifier(&relation.name)
        );
        // `relation.name` came from pg_catalog and is quoted as one identifier;
        // PostgreSQL cannot bind an identifier in this count projection.
        relation.row_count = sqlx::query_scalar(AssertSqlSafe(query))
            .fetch_one(pool)
            .await?;
    }

    let foreign_keys = sqlx::query(
        r#"
        SELECT
            constraint_row.conname AS constraint_name,
            source.relname AS source_relation,
            source_attribute.attname AS source_column,
            target.relname AS target_relation,
            target_attribute.attname AS target_column,
            NOT source_attribute.attnotnull AS source_nullable,
            EXISTS (
                SELECT 1
                FROM pg_catalog.pg_index unique_index
                WHERE unique_index.indrelid = source.oid
                  AND unique_index.indisunique
                  AND unique_index.indnatts = 1
                  AND source_attribute.attnum = ANY(unique_index.indkey)
            ) AS source_unique
        FROM pg_catalog.pg_constraint constraint_row
        JOIN pg_catalog.pg_class source ON source.oid = constraint_row.conrelid
        JOIN pg_catalog.pg_namespace namespace ON namespace.oid = source.relnamespace
        JOIN pg_catalog.pg_class target ON target.oid = constraint_row.confrelid
        JOIN LATERAL unnest(constraint_row.conkey, constraint_row.confkey)
            AS key_columns(source_number, target_number) ON true
        JOIN pg_catalog.pg_attribute source_attribute
            ON source_attribute.attrelid = source.oid
           AND source_attribute.attnum = key_columns.source_number
        JOIN pg_catalog.pg_attribute target_attribute
            ON target_attribute.attrelid = target.oid
           AND target_attribute.attnum = key_columns.target_number
        WHERE namespace.nspname = 'factory'
          AND constraint_row.contype = 'f'
        ORDER BY source.relname, constraint_row.conname, source_attribute.attnum
        "#,
    )
    .fetch_all(pool)
    .await?
    .into_iter()
    .map(|row| {
        Ok(ForeignKey {
            name: row.try_get("constraint_name")?,
            source_relation: row.try_get("source_relation")?,
            source_column: row.try_get("source_column")?,
            target_relation: row.try_get("target_relation")?,
            target_column: row.try_get("target_column")?,
            source_nullable: row.try_get("source_nullable")?,
            source_unique: row.try_get("source_unique")?,
        })
    })
    .collect::<Result<Vec<_>, sqlx::Error>>()?;

    let indexes = sqlx::query(
        r#"
        SELECT
            relation.relname AS relation_name,
            index_relation.relname AS index_name,
            index_row.indisprimary AS is_primary,
            index_row.indisunique AS is_unique,
            pg_catalog.pg_get_indexdef(index_row.indexrelid) AS definition
        FROM pg_catalog.pg_index index_row
        JOIN pg_catalog.pg_class relation ON relation.oid = index_row.indrelid
        JOIN pg_catalog.pg_class index_relation ON index_relation.oid = index_row.indexrelid
        JOIN pg_catalog.pg_namespace namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = 'factory'
        ORDER BY relation.relname, index_relation.relname
        "#,
    )
    .fetch_all(pool)
    .await?
    .into_iter()
    .map(|row| {
        Ok(Index {
            relation: row.try_get("relation_name")?,
            name: row.try_get("index_name")?,
            primary: row.try_get("is_primary")?,
            unique: row.try_get("is_unique")?,
            definition: row.try_get("definition")?,
        })
    })
    .collect::<Result<Vec<_>, sqlx::Error>>()?;

    let grants = sqlx::query(
        r#"
        SELECT grantee, table_name AS relation_name, NULL::text AS column_name, privilege_type
        FROM information_schema.role_table_grants
        WHERE table_schema = 'factory'
          AND grantee LIKE 'patchyard_%'
        UNION ALL
        SELECT grantee, table_name, column_name, privilege_type
        FROM information_schema.column_privileges
        WHERE table_schema = 'factory'
          AND (grantee LIKE 'patchyard_%' OR grantee = 'grafana_ro')
        ORDER BY grantee, relation_name, column_name NULLS FIRST, privilege_type
        "#,
    )
    .fetch_all(pool)
    .await?
    .into_iter()
    .map(|row| {
        Ok(GrantScope {
            grantee: row.try_get("grantee")?,
            relation: row.try_get("relation_name")?,
            column: row.try_get("column_name")?,
            privilege: row.try_get("privilege_type")?,
        })
    })
    .collect::<Result<Vec<_>, sqlx::Error>>()?;

    let roles = sqlx::query(
        r#"
        SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole
        FROM pg_catalog.pg_roles
        WHERE rolname LIKE 'patchyard_%' OR rolname = 'grafana_ro'
        ORDER BY rolname
        "#,
    )
    .fetch_all(pool)
    .await?
    .into_iter()
    .map(|row| {
        Ok(RoleScope {
            name: row.try_get("rolname")?,
            can_login: row.try_get("rolcanlogin")?,
            superuser: row.try_get("rolsuper")?,
            create_db: row.try_get("rolcreatedb")?,
            create_role: row.try_get("rolcreaterole")?,
        })
    })
    .collect::<Result<Vec<_>, sqlx::Error>>()?;

    Ok(SchemaCatalog {
        relations: relations.into_values().collect(),
        foreign_keys,
        indexes,
        grants,
        roles,
    })
}

/// Render a deterministic Mermaid ERD from the shared catalog.
#[must_use]
pub fn render_mermaid(catalog: &SchemaCatalog) -> String {
    let mut output = String::from(
        "%% Generated by factory-core::schema from a migrated PostgreSQL catalog.\n\
         %% Do not hand-edit; tools/check-state.sh byte-compares this projection.\n\
         erDiagram\n",
    );
    for relation in catalog.relations.iter().filter(|item| item.kind == "table") {
        let _ = writeln!(output, "    {} {{", mermaid_identifier(&relation.name));
        for column in &relation.columns {
            let marker = if column.primary_key {
                " PK"
            } else if column.unique {
                " UK"
            } else {
                ""
            };
            let nullable = if column.nullable { " nullable" } else { "" };
            let _ = writeln!(
                output,
                "        {} {}{}{}",
                mermaid_type(&column.data_type),
                mermaid_identifier(&column.name),
                marker,
                nullable
            );
        }
        output.push_str("    }\n");
    }
    for foreign_key in &catalog.foreign_keys {
        let target_cardinality = if foreign_key.source_nullable {
            "o|"
        } else {
            "||"
        };
        let source_cardinality = if foreign_key.source_unique {
            "o|"
        } else {
            "o{"
        };
        let _ = writeln!(
            output,
            "    {} {}--{} {} : \"{}\"",
            mermaid_identifier(&foreign_key.target_relation),
            target_cardinality,
            source_cardinality,
            mermaid_identifier(&foreign_key.source_relation),
            foreign_key.name
        );
    }
    output
}

fn quote_identifier(identifier: &str) -> String {
    format!("\"{}\"", identifier.replace('"', "\"\""))
}

fn mermaid_identifier(value: &str) -> String {
    value
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || character == '_' {
                character
            } else {
                '_'
            }
        })
        .collect()
}

fn mermaid_type(value: &str) -> String {
    let normalized = value
        .replace("timestamp with time zone", "timestamptz")
        .replace("character varying", "varchar")
        .replace(['(', ')', ','], "");
    mermaid_identifier(&normalized)
}

#[derive(Debug, Error)]
pub enum SchemaError {
    #[error("PostgreSQL catalog introspection failed: {0}")]
    Database(#[from] sqlx::Error),
}

#[cfg(test)]
mod tests {
    use super::{Column, Relation, SchemaCatalog, render_mermaid};

    #[test]
    fn mermaid_projection_is_deterministic() {
        let catalog = SchemaCatalog {
            relations: vec![Relation {
                name: "requests".to_owned(),
                kind: "table".to_owned(),
                row_count: 0,
                columns: vec![Column {
                    name: "id".to_owned(),
                    data_type: "uuid".to_owned(),
                    nullable: false,
                    primary_key: true,
                    unique: true,
                }],
            }],
            foreign_keys: Vec::new(),
            indexes: Vec::new(),
            grants: Vec::new(),
            roles: Vec::new(),
        };
        assert!(render_mermaid(&catalog).contains("uuid id PK"));
    }
}
