#include <unistd.h>
#include <stdio.h>
#include <string.h>
#include <limits.h>
int main(int argc,char **argv) {
    char path[PATH_MAX]; ssize_t n=readlink("/proc/self/exe",path,sizeof(path)-1);
    if(n<0 || n>=sizeof(path)-1) return 1;
    path[n]=0; char *slash=strrchr(path,'/'); if(!slash) return 1;
    if ((size_t)(slash-path)+sizeof("/RTXForge GUI.sh")>sizeof(path)) return 1;
    strcpy(slash,"/RTXForge GUI.sh");
    execl("/bin/bash","bash",path,(char*)NULL);
    perror("RTXForge GUI"); return 1;
}
