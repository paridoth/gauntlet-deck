/* Enumerate through Dolphin's own SDL runtime; no SDL build dependency. */
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

int main(void) {
  void *lib = dlopen("libSDL3.so.0", RTLD_NOW);
  if (lib) {
    _Bool (*init)(uint32_t) = dlsym(lib, "SDL_Init");
    uint32_t *(*list)(int *) = dlsym(lib, "SDL_GetGamepads");
    const char *(*name)(uint32_t) = dlsym(lib, "SDL_GetGamepadNameForID");
    void (*free_sdl)(void *) = dlsym(lib, "SDL_free");
    void (*quit)(void) = dlsym(lib, "SDL_Quit");
    if (!init || !list || !name || !free_sdl || !quit || !init(0x2000)) return 2;
    int count = 0;
    uint32_t *ids = list(&count);
    for (int i = 0; ids && i < count; ++i) {
      const char *n = name(ids[i]);
      if (n) puts(n);
    }
    free_sdl(ids);
    quit();
    return 0;
  }
  lib = dlopen("libSDL2-2.0.so.0", RTLD_NOW);
  if (!lib) return 2;
  int (*init)(uint32_t) = dlsym(lib, "SDL_Init");
  int (*count)(void) = dlsym(lib, "SDL_NumJoysticks");
  int (*is_gamepad)(int) = dlsym(lib, "SDL_IsGameController");
  const char *(*name)(int) = dlsym(lib, "SDL_GameControllerNameForIndex");
  void (*quit)(void) = dlsym(lib, "SDL_Quit");
  if (!init || !count || !is_gamepad || !name || !quit || init(0x2000) != 0) return 2;
  for (int i = 0; i < count(); ++i) {
    const char *n = is_gamepad(i) ? name(i) : NULL;
    if (n) puts(n);
  }
  quit();
  return 0;
}
