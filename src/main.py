import re
import os
from datetime import datetime, timedelta

# Path to your SQL dump
sql_file_path = '../data/mysql-schema.sql'

# Where to save the generated migrations
output_dir = '../generated_migrations'
os.makedirs(output_dir, exist_ok=True)

# Read the SQL file
with open(sql_file_path, 'r', encoding='utf-8') as file:
    sql_content = file.read()

# Find all CREATE TABLE blocks
create_table_blocks = re.findall(r'CREATE TABLE\s+`([^`]*)`\s*\((.*?)\)\s*ENGINE=', sql_content, re.S)

# Start time for migration filenames
base_time = datetime.now()

# Migration template
migration_stub = """<?php

use Illuminate\\Database\\Migrations\\Migration;
use Illuminate\\Database\\Schema\\Blueprint;
use Illuminate\\Support\\Facades\\Schema;

return new class extends Migration
{{
    public function up(): void
    {{
        Schema::create('{table_name}', function (Blueprint $table) {{
{columns}
        }});
    }}

    public function down(): void
    {{
        Schema::dropIfExists('{table_name}');
    }}
}};
"""


# Helper: convert SQL type to Laravel schema
def parse_sql_column(sql_line):
    match = re.match(r'`([^`]*)`\s+([a-zA-Z0-9\(\)]+)(.*)', sql_line)
    if not match:
        return None

    field_name, field_type, options = match.groups()
    field = ''

    # Normalize options
    options = options.lower()

    # Mapping SQL types to Laravel Schema methods
    if 'bigint' in field_type:
        if 'unsigned' in options:
            if 'auto_increment' in options:
                field = f"$table->bigIncrements('{field_name}')"
            else:
                field = f"$table->unsignedBigInteger('{field_name}')"
        else:
            field = f"$table->bigInteger('{field_name}')"
    elif 'int' in field_type:
        if 'unsigned' in options:
            if 'auto_increment' in options:
                field = f"$table->increments('{field_name}')"
            else:
                field = f"$table->unsignedInteger('{field_name}')"
        else:
            field = f"$table->integer('{field_name}')"
    elif 'varchar' in field_type:
        size = re.search(r'\((\d+)\)', field_type)
        if size:
            field = f"$table->string('{field_name}', {size.group(1)})"
        else:
            field = f"$table->string('{field_name}')"
    elif 'text' in field_type:
        field = f"$table->text('{field_name}')"
    elif 'datetime' in field_type:
        field = f"$table->dateTime('{field_name}')"
    elif 'timestamp' in field_type:
        field = f"$table->timestamp('{field_name}')"
    elif 'date' in field_type:
        field = f"$table->date('{field_name}')"
    elif 'tinyint(1)' in field_type or ('tinyint' in field_type and '1' in field_type):
        field = f"$table->boolean('{field_name}')"
    elif 'decimal' in field_type:
        precision = re.findall(r'\((\d+),(\d+)\)', field_type)
        if precision:
            field = f"$table->decimal('{field_name}', {precision[0][0]}, {precision[0][1]})"
        else:
            field = f"$table->decimal('{field_name}')"
    else:
        field = f"// {sql_line}"  # fallback comment if type unknown

    # Handle NULL / DEFAULT
    if 'not null' not in options:
        field += '->nullable()'
    if 'default' in options:
        default_val = re.search(r"default\s+'([^']*)'", options)
        if not default_val:
            default_val = re.search(r'default\s+([^\s,]+)', options)
        if default_val:
            default = default_val.group(1)
            if default.lower() == 'null':
                pass  # already handled nullable
            else:
                field += f"->default('{default}')"

    return field + ';'


# Parse foreign keys separately
def parse_constraint(constraint_line):
    if constraint_line.startswith('PRIMARY KEY'):
        pk_match = re.search(r'\((.*?)\)', constraint_line)
        if pk_match:
            cols = pk_match.group(1).replace('`', '').split(',')
            if len(cols) == 1:
                return f"$table->primary('{cols[0].strip()}');"
            else:
                return f"$table->primary([{', '.join([f'\'{col.strip()}\'' for col in cols])}]);"
    if constraint_line.startswith('CONSTRAINT') and 'FOREIGN KEY' in constraint_line:
        match = re.search(r'FOREIGN KEY\s+\(`([^`]*)`\)\s+REFERENCES\s+`([^`]*)`\s+\(`([^`]*)`\)', constraint_line)
        if match:
            local_col, foreign_table, foreign_col = match.groups()
            return f"$table->foreign('{local_col}')->references('{foreign_col}')->on('{foreign_table}');"
    return f"// {constraint_line}"


for i, (table_name, columns_block) in enumerate(create_table_blocks):
    # Prepare timestamp
    timestamp = (base_time + timedelta(seconds=i)).strftime('%Y_%m_%d_%H%M%S')

    # Process columns and constraints
    column_lines = []
    for line in columns_block.splitlines():
        line = line.strip().rstrip(',')
        if not line:
            continue
        if line.startswith('`'):
            parsed = parse_sql_column(line)
            if parsed:
                column_lines.append(' ' * 12 + parsed)
        else:
            parsed = parse_constraint(line)
            if parsed:
                column_lines.append(' ' * 12 + parsed)

    columns_code = "\n".join(column_lines)

    # Fill the stub
    migration_content = migration_stub.format(
        table_name=table_name,
        columns=columns_code
    )

    # Create the migration filename
    file_name = f"{timestamp}_create_{table_name}_table.php"
    file_path = os.path.join(output_dir, file_name)

    # Write the file
    with open(file_path, 'w', encoding='utf-8') as migration_file:
        migration_file.write(migration_content)

    print(f"Generated: {file_path}")
