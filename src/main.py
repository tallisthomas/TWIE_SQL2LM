import re

if __name__ == '__main__':
    # Read the SQL file
    with open('../data/mysql-schema.sql', 'r', encoding='utf-8') as file:
        sql_content = file.read()

    # Find all CREATE TABLE blocks
    create_table_blocks = re.findall(r'CREATE TABLE\s+`([^`]*)`\s*\((.*?)\)\s*ENGINE=', sql_content, re.S)

    tables = {}

    for table_name, columns_block in create_table_blocks:
        # Split the columns block into lines
        columns = []
        constraints = []
        for line in columns_block.splitlines():
            line = line.strip().rstrip(',')
            if not line:
                continue
            if line.startswith('`'):
                columns.append(line)
            else:
                constraints.append(line)

        tables[table_name] = {
            'columns': columns,
            'constraints': constraints
        }

    # Now, print the result nicely
    for table, details in tables.items():
        print(f"Table: {table}")
        print("Columns:")
        for column in details['columns']:
            print(f"  {column}")
        print("Constraints:")
        for constraint in details['constraints']:
            print(f"  {constraint}")
        print("-" * 40)
