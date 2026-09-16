/* Native file-manager launcher; delegates to the adjacent desktop entry. */
#include <unistd.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
int main(int argc, char **argv) {
    char path[PATH_MAX];
    ssize_t size = readlink("/proc/self/exe", path, sizeof(path)-9);
    if (size < 0 || size >= sizeof(path)-9) { perror("launcher path"); return 1; }
    path[size] = 0;
    strcat(path, ".desktop");
    if (argc == 2 && strcmp(argv[1], "--check") == 0) {
        if (access(path, R_OK)) { perror(path); return 1; }
        puts(path); return 0;
    }
    execl("/usr/bin/gio", "gio", "launch", path, (char *)0);
    perror("launch game shortcut");
    return 1;
}
