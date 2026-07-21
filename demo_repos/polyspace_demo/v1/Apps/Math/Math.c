#include <stdint.h>

int32_t divide_unchecked(int32_t numerator, int32_t denominator)
{
    return numerator / denominator;
}

int32_t divide_guarded(int32_t numerator, int32_t denominator)
{
    if (denominator == 0) {
        return 0;
    }
    return numerator / denominator;
}
