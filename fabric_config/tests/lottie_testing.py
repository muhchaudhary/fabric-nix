from lottie import LottieAnimationWidget
from fabric.widgets import WaylandWindow
import fabric


from rlottie_python import LottieAnimation, LottieAnimationProperty
import ctypes

anim = LottieAnimation.from_file("/home/muhammad/Downloads/circle.json")


anim.lottie_animation_property_override(
    LottieAnimationProperty.LOTTIE_ANIMATION_PROPERTY_FILLCOLOR,
    "Animation.Layer.Ellipse.Fill",
    ctypes.c_double(1.0),
    ctypes.c_double(0.0),
    ctypes.c_double(0.0),
)

anim.save_animation("/home/muhammad/Downloads/circle.gif")


WaylandWindow(
    children=LottieAnimationWidget(
        lottie_animation=anim, do_loop=False, scale=0.25, draw_frame=1
    ),
    layer="top",
    anchor="center",
    style="background-color: transparent;",
)

fabric.start()
