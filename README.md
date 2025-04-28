**Laravel Schema-Dump Migration Generator**

A lightweight tool to convert a full Laravel schema-dump (`php artisan schema:dump`) into fresh, standalone migration files. Ideal for legacy codebases with tangled history of creates, alters, drop columns, and outdated dependencies that can make `php artisan migrate:fresh` unreliable or slow.

---

## 🔍 Motivation

- **Legacy Migrations**: Over time, projects accumulate hundreds of SQL migrations—some altering, others adding or dropping columns—often relying on packages no longer present. This can break or slow down fresh installs and automated tests.
- **Faster Tests**: In containerized or VM environments using MySQL/Postgres, running full migrations on each test run is a bottleneck. Generating a clean set of `create_table` migrations plus a single foreign-key migration speeds things up.

---

## 🚀 How It Works

1. **Place your schema dump**
   - Default input: `../data/mysql‑schema.sql` (output of `php artisan schema:dump`).
2. **Run the generator**
   ```bash
   python generate_migrations.py
   ```
   - The script reads `../data/mysql‑schema.sql`, parses each `CREATE TABLE` block, and:
     - Emits one `create_<table>_table.php` migration per table (columns, primary keys, indexes).
     - Emits a single `add_foreign_keys_to_tables.php` that applies all foreign keys in `up()` and drops them in `down()`.
3. **Review & Apply**
   - Move the generated folder `../generated_migrations/{timestamp}/` into your Laravel project’s `database/migrations/`.
   - Run `php artisan migrate` (or include in your test bootstrap process).

---

## ⚠️ Limitations & Caveats

- **Type Mapping**: Most common types (int, bigint, tinyint → boolean/integer, varchar, text, datetime, timestamp, date, time, decimal, float, double, enum, json) are auto-converted. Unrecognized or complex types (e.g., spatial, bitfields) remain commented out for manual review.
- **ENUM Values**: Inserted verbatim; you may need to adjust syntax or defaults for compatibility.
- **Indexes**: Only primary keys and foreign keys are fully generated. Other indexes (unique, fulltext, spatial) may require manual re-creation.
- **Foreign Key Options**: Advanced options like `ON DELETE CASCADE`, `ON UPDATE` clauses are not parsed and appear as comments.
- **Schema Format**: Expects Laravel’s dumped SQL format (`CREATE TABLE ... ENGINE=...`). Custom SQL or additional DDL statements may be ignored.
- **SQLite Testing**: While most types map to SQLite-friendly definitions, always verify in your test environment.

---

## 📝 Disclaimer

This tool is provided **as-is**, for accelerating the reorganization of legacy migration histories. There is **no guarantee** that the generated migrations will run without minor manual adjustments. **Always** review, test in a safe branch, and update as needed before merging.

---

## 🎯 Usage Tips

- **Regenerate on changes**: After updating your database schema in production, simply regenerate by dumping with `php artisan schema:dump` and re-running this script.
- **Version control**: Commit the generated migrations folder to track changes over time.
