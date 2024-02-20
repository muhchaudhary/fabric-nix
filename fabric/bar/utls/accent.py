from colorthief import ColorThief


def grab_color(image_path: str, n: int):
    c_t = ColorThief(image_path)
    return c_t.get_color(n)
