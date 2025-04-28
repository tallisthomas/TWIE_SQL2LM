import re
import os
from datetime import datetime

# ---------------------------------------------------
# Configuration
# ---------------------------------------------------
sql_file_path = '../data/mysql-schema.sql'
output_dir = '../generated_migrations/' + datetime.now().strftime('%Y%m%d_%H%M%S')
os.makedirs(output_dir, exist_ok=True)
# ---------------------------------------------------
# /Configuration
# ---------------------------------------------------

# Read the SQL dump
with open(sql_file_path, 'r', encoding='utf-8') as f:
    sql_content = f.read()

# Remove SQL comments to avoid parsing issues
sql_content = re.sub(r'/\*.*?\*/', '', sql_content, flags=re.S)
sql_content = re.sub(r'--.*$', '', sql_content, flags=re.M)
sql_content = re.sub(r'#.*$', '', sql_content, flags=re.M)

# Extract CREATE TABLE blocks
create_blocks = re.findall(
    r'CREATE TABLE\s+`([^`]*)`\s*\((.*?)\)\s*ENGINE=',
    sql_content,
    re.S
)
# Exclude Laravel's own migrations table
create_blocks = [(tbl, blk) for tbl, blk in create_blocks if tbl != 'migrations']

# ---------------------------------------------------
# Migration stubs
# ---------------------------------------------------
create_stub = '''<?php

use Illuminate\\Database\\Migrations\\Migration;
use Illuminate\\Database\\Schema\\Blueprint;
use Illuminate\\Support\\Facades\\Schema;

return new class extends Migration
{{
    public function up(): void
    {{
        Schema::create('{table}', function (Blueprint $table) {{
{body}
        }});
    }}

    public function down(): void
    {{
        Schema::dropIfExists('{table}');
    }}
}};
'''

foreign_stub = '''<?php

use Illuminate\\Database\\Migrations\\Migration;
use Illuminate\\Database\\Schema\\Blueprint;
use Illuminate\\Support\\Facades\\Schema;

return new class extends Migration
{{
    public function up(): void
    {{
{up_methods}
    }}

    public function down(): void
    {{
{down_methods}
    }}
}};
'''

# ---------------------------------------------------
# Helpers
# ---------------------------------------------------
def parse_sql_column(line: str) -> str:
    m = re.match(r'`([^`]*)`\s+([^\s]+)(.*)', line)
    if not m:
        return f"// {line}"
    name, ftype, rest = m.groups()
    ft = ftype.lower()
    opts = rest.lower()
    code = None
    # Map SQL types -> Laravel Schema
    if ft.startswith('enum'):
        vals = re.findall(r"'([^']*)'", ftype)
        code = f"$table->enum('{name}', {vals})"
    elif 'json' in ft:
        code = f"$table->json('{name}')"
    elif ft.startswith('double'):
        prec = re.findall(r'\((\d+),(\d+)\)', ft)
        code = f"$table->double('{name}'" + (f", {prec[0][0]}, {prec[0][1]}" if prec else "") + ")"
    elif ft.startswith('float'):
        code = f"$table->float('{name}')"
    elif ft.startswith('decimal'):
        prec = re.findall(r'\((\d+),(\d+)\)', ft)
        code = f"$table->decimal('{name}'" + (f", {prec[0][0]}, {prec[0][1]}" if prec else "") + ")"
    elif re.match(r'tinyint\s*\(1\)', ft):
        code = f"$table->boolean('{name}')"
    elif ft.startswith('tinyint'):
        code = f"$table->unsignedTinyInteger('{name}')" if 'unsigned' in opts else f"$table->tinyInteger('{name}')"
    elif ft.startswith('smallint'):
        code = f"$table->unsignedSmallInteger('{name}')" if 'unsigned' in opts else f"$table->smallInteger('{name}')"
    elif ft.startswith('bigint'):
        if 'unsigned' in opts:
            code = f"$table->bigIncrements('{name}')" if 'auto_increment' in opts else f"$table->unsignedBigInteger('{name}')"
        else:
            code = f"$table->bigInteger('{name}')"
    elif re.match(r'int', ft):
        if 'unsigned' in opts:
            code = f"$table->increments('{name}')" if 'auto_increment' in opts else f"$table->unsignedInteger('{name}')"
        else:
            code = f"$table->integer('{name}')"
    elif ft.startswith('varchar'):
        size = re.search(r'\((\d+)\)', ft)
        code = f"$table->string('{name}', {size.group(1)})" if size else f"$table->string('{name}')"
    elif ft.startswith('text'):
        code = f"$table->text('{name}')"
    elif ft.startswith('datetime'):
        code = f"$table->dateTime('{name}')"
    elif ft.startswith('timestamp'):
        code = f"$table->timestamp('{name}')"
    elif ft.startswith('time'):
        code = f"$table->time('{name}')"
    elif ft.startswith('date'):
        code = f"$table->date('{name}')"
    # Fallback for unknown
    if code is None:
        return f"// {line}"
    # Nullability
    if 'not null' not in opts:
        code += '->nullable()'
    # Default value (escaped)
    dv = re.search(r"default\s+'([^']*)'", opts) or re.search(r"default\s+([^, ]+)", opts)
    if dv and dv.group(1).lower() != 'null':
        val = dv.group(1).replace("'", "\\'")
        code += f"->default('{val}')"
    # Column comment
    cm = re.search(r"comment\s+'([^']*)'", rest, re.I)
    if cm:
        comment = cm.group(1).replace("'", "\\'")
        code += f"->comment('{comment}')"
    return code + ';'

def parse_constraint(line: str) -> str | None:
    if line.lower().startswith('primary key'):
        cols = re.search(r'\((.*?)\)', line).group(1).replace('`','').split(',')
        if len(cols)==1:
            return f"$table->primary('{cols[0].strip()}');"
        arr = ', '.join(f"'{c.strip()}'" for c in cols)
        return f"$table->primary([{arr}]);"
    if 'foreign key' in line.lower():
        fk = re.search(r'FOREIGN KEY\s+\(`([^`]*)`\)\s+REFERENCES\s+`([^`]*)`\s+\(`([^`]*)`\)', line, re.I)
        if fk:
            local, ref_table, ref_col = fk.groups()
            return f"$table->foreign('{local}')->references('{ref_col}')->on('{ref_table}');"
    return None

def is_foreign(line: str) -> bool:
    return 'foreign key' in line.lower()

def parse_drop_fk(line: str) -> str | None:
    m = re.search(r'FOREIGN KEY\s+\(`([^`]*)`\)', line)
    return f"$table->dropForeign(['{m.group(1)}']);" if m else None

# ---------------------------------------------------
# Generate create_<table>_table.php migrations
# ---------------------------------------------------
foreigns = {}
for table, block in create_blocks:
    auto_pks = set()
    body_lines = []
    for raw in block.splitlines():
        line = raw.strip().rstrip(',')
        if not line:
            continue
        if line.startswith('`'):
            code_line = parse_sql_column(line)
            body_lines.append(' ' * 12 + code_line)
            # Track auto-increment PK
            m_inc = re.match(r"\$table->(increments|bigIncrements)\('(.*?)'\)", code_line)
            if m_inc:
                auto_pks.add(m_inc.group(2))
        else:
            if is_foreign(line):
                fk = parse_constraint(line)
                foreigns.setdefault(table, []).append((line, fk))
            else:
                c = parse_constraint(line)
                if c:
                    body_lines.append(' ' * 12 + c)
    # Remove explicit pk duplicates
    final_lines = []
    for ln in body_lines:
        if '$table->primary(' in ln:
            pk_col = re.search(r"primary\('(.*?)'\)", ln).group(1)
            if pk_col in auto_pks:
                continue
        final_lines.append(ln)
    content = create_stub.format(table=table, body="\n".join(final_lines))
    filename = f"create_{table}_table.php"
    with open(os.path.join(output_dir, filename), 'w', encoding='utf-8') as mf:
        mf.write(content)
    print(f"Created table migration: {filename}")

# ---------------------------------------------------
# Generate z_add_foreign_keys_to_tables.php
# (z_ to make sure it's going to run after all create_xxx.php files)
# ---------------------------------------------------
up_lines = []
down_lines = []
for table, entries in foreigns.items():
    if table == 'migrations':
        continue
    up_lines.append(f"        Schema::table('{table}', function (Blueprint $table) {{")
    for raw, fk in entries:
        if fk:
            up_lines.append(' ' * 12 + fk)
            drop = parse_drop_fk(raw)
            if drop:
                down_lines.append(f"        Schema::table('{table}', function (Blueprint $table) {{")
                down_lines.append(' ' * 12 + drop)
                down_lines.append("        });")
    up_lines.append("        });")
foreign_content = foreign_stub.format(
    up_methods="\n".join(up_lines),
    down_methods="\n".join(down_lines)
)
fk_filename = "z_add_foreign_keys_to_tables.php"
with open(os.path.join(output_dir, fk_filename), 'w', encoding='utf-8') as mf:
    mf.write(foreign_content)
print(f"Created foreign-keys migration: {fk_filename}")
