/*
 * egctl_ref.c - reference oracle for the protocol unit tests.
 *
 * Contains the EXACT arithmetic copied from egctl.c (MIT, Vitaly Sinilin,
 * https://github.com/unterwulf/egctl) so the Python port can be checked
 * byte-for-byte against the canonical C implementation.
 *
 * Usage (all args are hex strings, no spaces):
 *   egctl_ref solve   <key8> <task4>           -> 4-byte response
 *   egctl_ref decrypt <key8> <task4> <stat4>   -> 4 raw state bytes (sockets 1..4)
 *   egctl_ref encrypt <key8> <task4> <ctrl4>   -> 4-byte control frame
 * Output: hex string of the result bytes.
 */

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define SOCKET_COUNT 4

static int hex2bytes(const char *hex, uint8_t *out, int max)
{
    int n = strlen(hex);
    if (n % 2 != 0 || n / 2 > max)
        return -1;
    for (int i = 0; i < n / 2; i++)
        sscanf(hex + 2 * i, "%2hhx", &out[i]);
    return n / 2;
}

static void print_hex(const uint8_t *buf, int n)
{
    for (int i = 0; i < n; i++)
        printf("%02x", buf[i]);
    printf("\n");
}

int main(int argc, char *argv[])
{
    if (argc != 5) {
        fprintf(stderr, "usage: %s <solve|decrypt|encrypt> <key8> <task4> <data4|->\n", argv[0]);
        return 2;
    }

    uint8_t key[8], task[4], data[4];
    if (hex2bytes(argv[2], key, 8) != 8) { fprintf(stderr, "bad key\n"); return 2; }
    if (hex2bytes(argv[3], task, 4) != 4) { fprintf(stderr, "bad task\n"); return 2; }

    if (!strcmp(argv[1], "solve")) {
        /* egctl.c authorize() */
        uint16_t loword = ((task[0] ^ key[2]) * key[0])
                          ^ (key[6] | (key[4] << 8)) ^ task[2];
        uint16_t hiword = ((task[1] ^ key[3]) * key[1])
                          ^ (key[7] | (key[5] << 8)) ^ task[3];
        uint8_t res[4] = {
            (uint8_t)(loword & 0xff), (uint8_t)(loword >> 8),
            (uint8_t)(hiword & 0xff), (uint8_t)(hiword >> 8),
        };
        print_hex(res, 4);
        return 0;
    }

    if (hex2bytes(argv[4], data, 4) != 4) { fprintf(stderr, "bad data\n"); return 2; }

    if (!strcmp(argv[1], "decrypt")) {
        /* egctl.c decrypt_status() -- data == statcryp */
        uint8_t st[SOCKET_COUNT];
        for (int i = 0; i < SOCKET_COUNT; i++)
            st[i] = (((data[3 - i] - key[1]) ^ key[0]) - task[3]) ^ task[2];
        print_hex(st, 4);
        return 0;
    }

    if (!strcmp(argv[1], "encrypt")) {
        /* egctl.c send_controls() -- data == ctrl opcodes per socket */
        uint8_t cc[SOCKET_COUNT];
        for (int i = 0; i < SOCKET_COUNT; i++)
            cc[i] = (((data[3 - i] ^ task[2]) + task[3]) ^ key[0]) + key[1];
        print_hex(cc, 4);
        return 0;
    }

    fprintf(stderr, "unknown mode %s\n", argv[1]);
    return 2;
}
