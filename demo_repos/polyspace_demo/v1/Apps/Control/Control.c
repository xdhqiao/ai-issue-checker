#include <stdint.h>

#define TABLE_SIZE 4

int32_t read_table(int32_t index)
{
    static const int32_t table[TABLE_SIZE] = {10, 20, 30, 40};
    return table[index];
}

int32_t read_table_checked(int32_t index)
{
    static const int32_t table[TABLE_SIZE] = {10, 20, 30, 40};
    if ((index < 0) || (index >= TABLE_SIZE)) {
        return -1;
    }
    return table[index];
}
