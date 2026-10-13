#define _GNU_SOURCE
#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int exists_exec(const char *name) {
    const char *path = getenv("PATH");
    if (!path || !*path) return 0;
    char *copy = strdup(path);
    if (!copy) return 0;
    int found = 0;
    for (char *save = NULL, *dir = strtok_r(copy, ":", &save); dir; dir = strtok_r(NULL, ":", &save)) {
        char candidate[PATH_MAX];
        if (!*dir) dir = ".";
        if (snprintf(candidate, sizeof(candidate), "%s/%s", dir, name) >= (int)sizeof(candidate)) continue;
        if (access(candidate, X_OK) == 0) { found = 1; break; }
    }
    free(copy);
    return found;
}

static void gui_error(const char *msg) {
    if (exists_exec("zenity")) {
        execlp("zenity", "zenity", "--error", "--title=RTXForge", "--text", msg, (char *)NULL);
    }
    if (exists_exec("notify-send")) {
        execlp("notify-send", "notify-send", "RTXForge launcher error", msg, (char *)NULL);
    }
    fprintf(stderr, "%s\n", msg);
}

int main(int argc, char **argv) {
    char exe[PATH_MAX];
    ssize_t n = readlink("/proc/self/exe", exe, sizeof(exe) - 1);
    if (n < 0) {
        fprintf(stderr, "Unable to locate launcher: %s\n", strerror(errno));
        return 1;
    }
    exe[n] = '\0';

    char *slash = strrchr(exe, '/');
    if (!slash) return 1;
    *slash = '\0';
    const char *dir = exe;

    char script[PATH_MAX];
    if (snprintf(script, sizeof(script), "%s/START HERE.sh", dir) >= (int)sizeof(script)) {
        fprintf(stderr, "Package path is too long.\n");
        return 1;
    }
    if (access(script, R_OK) != 0) {
        gui_error("START HERE.sh is missing from the package folder. Extract the complete package before launching.");
        return 1;
    }

    if (argc > 1 && strcmp(argv[1], "--self-test") == 0) {
        printf("Launcher: %s/RUN RTXFORGE\n", dir);
        printf("Menu:     %s\n", script);
        printf("Readable: yes\n");
        printf("Terminal candidates:\n");
        const char *terms[] = {"xdg-terminal-exec", "ptyxis", "gnome-terminal", "kgx", "konsole", "xterm", NULL};
        for (int i = 0; terms[i]; ++i) printf("  %-18s %s\n", terms[i], exists_exec(terms[i]) ? "FOUND" : "not found");
        return 0;
    }

    if (chdir(dir) != 0) {
        gui_error("Could not enter the extracted RTXForge package folder.");
        return 1;
    }

    /* If invoked from an existing interactive terminal, reuse it. */
    if (isatty(STDIN_FILENO) && isatty(STDOUT_FILENO)) {
        execlp("bash", "bash", script, (char *)NULL);
        perror("bash");
        return 1;
    }

    /* Fedora/Bazzite 44 ships xdg-terminal-exec; prefer the desktop's configured terminal. */
    if (exists_exec("xdg-terminal-exec"))
        execlp("xdg-terminal-exec", "xdg-terminal-exec", "bash", script, (char *)NULL);

    /* Bazzite GNOME / Fedora GNOME default terminal. */
    if (exists_exec("ptyxis"))
        execlp("ptyxis", "ptyxis", "--working-directory", dir, "--", "bash", script, (char *)NULL);

    if (exists_exec("gnome-terminal"))
        execlp("gnome-terminal", "gnome-terminal", "--working-directory", dir, "--", "bash", script, (char *)NULL);

    if (exists_exec("kgx"))
        execlp("kgx", "kgx", "--working-directory", dir, "--", "bash", script, (char *)NULL);

    if (exists_exec("konsole"))
        execlp("konsole", "konsole", "--workdir", dir, "-e", "bash", script, (char *)NULL);

    if (exists_exec("xterm"))
        execlp("xterm", "xterm", "-e", "bash", script, (char *)NULL);

    gui_error("No supported terminal application was found. Run START HERE.sh from a terminal instead.");
    return 1;
}
