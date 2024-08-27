# FileTable

import csv

def intify(x):
    try:
        return int(x)
    except ValueError:
        return x

class FileTable:
    def __init__(self):
        self.column_keys = []
        self.column_count = 0
        self.row_data = []
        self.row_count = 0
        self.id_key = None
        self.id_index = -1
        self.key_index_map = {}
        self.id_row_map = {}

    def transform_row(self, row):
        # Check if the row has the same number of cells as the first row (column_keys)
        # and the element at self.id_index is not an empty string
        if len(row) == self.column_count and row[self.id_index] != "":
            return list(map(intify, row))
        else:
            return None

    def ingest_csv(self, file_path, id_key="id", heading_rows_to_skip=1):
        with open(file_path, mode='r', newline='', encoding='utf-8') as file:
            reader = csv.reader(file)
            
            # Skip the specified number of heading rows
            for _ in range(heading_rows_to_skip):
                next(reader, None)

            # Read the first meaningful row and save it to column_keys
            self.column_keys = next(reader, None)
            
            if self.column_keys is None:
                return  # Return if there are no rows

            # Set the column_count to the length of the column_keys
            self.column_count = len(self.column_keys)

            # Set the id_key to the provided value
            self.id_key = id_key

            # Create the key_index_map dictionary
            self.key_index_map = {key: index for index, key in enumerate(self.column_keys)}

            # Set the id_index to the integer which is the mapping of id_key
            self.id_index = self.key_index_map.get(id_key, -1)

            # Read and process the remaining rows
            row_index = 0
            for row in reader:
                transformed_row = self.transform_row(row)
                if transformed_row is not None:
                    self.row_data.append(transformed_row)
                    # Add an element to the id_row_map dictionary
                    row_id = transformed_row[self.id_index]
                    prior_row = self.id_row_map.get(row_id, None)
                    if prior_row is not None:
                        raise KeyError(f"Another row with ID '{row_id}' was previously ingested")
                    self.id_row_map[row_id] = row_index
                    row_index += 1

            # Set the row_count to the value of row_index
            self.row_count = row_index

    def column_index(self, column_key):
        # Return the index of column_key in the column_keys list, or None if not found
        return self.key_index_map.get(column_key, None)

    def get_cell(self, id, column):
        # Coerce the "id" argument to an integer
        id = intify(id)
        # Return the column-th element in the id-th element of the row_data
        row_idx = self.id_row_map.get(id, None)
        if row_idx is not None:
            col_idx = self.column_index(column)
            if col_idx is not None:
                return self.row_data[row_idx][col_idx]
            else:
                raise KeyError(f"Column {column} not defined")
        else:
            raise KeyError(f"Row for ID {self.id_key}={id} not found")

    def set_cell(self, id, column, new_value):
        # Coerce the "id" and "new_value" arguments to integers
        id = intify(id)
        new_value = intify(new_value)
        # Update the column-th element in the id-th element of the row_data to be equal to new_value
        row_idx = self.id_row_map.get(id, None)
        if row_idx is not None:
            col_idx = self.column_index(column)
            if col_idx is not None:
                self.row_data[row_idx][col_idx] = new_value
                return new_value
            else:
                raise KeyError(f"Column {column} not defined")
        else:
            raise KeyError(f"Row for ID {self.id_key}={id} not found")

# Example usage:
# file_table = FileTable()
# file_table.ingest_csv('path_to_your_file.csv', 'some_id_key')
# print(file_table.column_keys)
# print(file_table.column_count)
# print(file_table.row_data)
# print(file_table.row_count)
# print(file_table.id_key)
# print(file_table.id_index)
# print(file_table.key_index_map)
# print(file_table.id_row_map)
# print(file_table.column_index('some_column_key'))
# print(file_table.get_cell('some_id', 'some_column_key'))
# print(file_table.set_cell('some_id', 'some_column_key', 'new_value'))
# print(file_table.get_cell('some_id', 'some_column_key'))