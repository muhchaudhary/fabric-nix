import gi
import OpenGL.GL as GL
from typing import cast, Literal
from collections.abc import Iterable, Callable
from OpenGL.GL.shaders import compileShader, compileProgram

from fabric import Application
from fabric.widgets.box import Box
from fabric.widgets.scale import Scale
from fabric.widgets.label import Label
from fabric.widgets.widget import Widget
from fabric.widgets.window import Window
from fabric.widgets.wayland import WaylandWindow


gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib


VERT_SHADER = """
#version 330

in vec2 position;

void main() {
    gl_Position = vec4(position, 0.0, 1.0);
}
"""


FRAG_SHADER = """
#version 330

uniform vec3 iResolution;           // viewport resolution (in pixels)
uniform float iTime;                 // shader playback time (in seconds)
uniform float iTimeDelta;            // render time (in seconds)
uniform float iFrameRate;            // shader frame rate
uniform int iFrame;                  // shader playback frame
uniform float iChannelTime[4];       // channel playback time (in seconds)
uniform vec3 iChannelResolution[4];  // channel resolution (in pixels)
uniform vec4 iMouse;                 // mouse pixel coords. xy: current (if MLB down), zw: click
uniform sampler2D iChannel0;         // input channel. XX = 2D/Cube
uniform sampler2D iChannel1;
uniform sampler2D iChannel2;
uniform sampler2D iChannel3;
uniform vec4 iDate;                  // (year, month, day, time in seconds)
uniform float iSampleRate;           // sound sample rate (i.e., 44100)

"""

FRAG_MAIN_FUNC = """
void main() {
    mainImage(gl_FragColor, gl_FragCoord.xy);
}

"""


"""
uniform vec3      iResolution;           // viewport resolution (in pixels)
uniform float     iTime;                 // shader playback time (in seconds)
uniform float     iTimeDelta;            // render time (in seconds)
uniform float     iFrameRate;            // shader frame rate
uniform int       iFrame;                // shader playback frame
uniform float     iChannelTime[4];       // channel playback time (in seconds)
uniform vec3      iChannelResolution[4]; // channel resolution (in pixels)
uniform vec4      iMouse;                // mouse pixel coords. xy: current (if MLB down), zw: click
uniform samplerXX iChannel0..3;          // input channel. XX = 2D/Cube
uniform vec4      iDate;                 // (year, month, day, time in seconds)
uniform float     iSampleRate;           // sound sample rate (i.e., 44100)

"""


class ShadertoyCompileError(Exception): ...


class Shadertoy(Gtk.GLArea, Widget):
    def __init__(
        self,
        shader_buffer: str,
        unifroms_map: dict[str, Callable] | None = None,
        name: str | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
        style_classes: Iterable[str] | str | None = None,
        tooltip_text: str | None = None,
        tooltip_markup: str | None = None,
        h_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        v_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        h_expand: bool = False,
        v_expand: bool = False,
        size: Iterable[int] | int | None = None,
        **kwargs,
    ):
        Gtk.GLArea.__init__(
            self  # type: ignore
        )
        Widget.__init__(
            self,
            name,
            visible,
            all_visible,
            style,
            style_classes,
            tooltip_text,
            tooltip_markup,
            h_align,
            v_align,
            h_expand,
            v_expand,
            size,
            **kwargs,
        )
        self.shader_buffer = FRAG_SHADER + shader_buffer + FRAG_MAIN_FUNC
        self.unifroms_map = unifroms_map or {}

        # GLArea widget settings
        self.set_required_version(3, 3)
        self.set_has_depth_buffer(False)
        self.set_has_stencil_buffer(False)
        self.connect("render", self.on_render)
        self.connect("resize", self.on_glarea_resize)
        self.connect("realize", self.on_realize)

        # timer
        self.start_time = GLib.get_monotonic_time() / 1e6
        self.frame_time = self.start_time
        self.frame_count = 0

        # to avoid a constant framerate
        # we tell gtk to render a frame whenever possible
        self.add_tick_callback(self.on_tick)

    def on_realize(self, *_):
        ctx = self.get_context()
        ctx.make_current()

        if self.get_error() is not None:
            raise RuntimeError  # TODO: document...

        self.program = self.do_bake_shader()

        self.quad_vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.quad_vbo)

        # suggestion: use numpy arrays
        quad_verts = [
            -1.0,
            -1.0,
            1.0,
            -1.0,
            -1.0,
            1.0,
            1.0,
            1.0,
        ]

        # list -> arraybuf
        array_type = GL.GLfloat * len(quad_verts)
        GL.glBufferData(
            GL.GL_ARRAY_BUFFER,
            len(quad_verts) * 4,
            array_type(*quad_verts),
            GL.GL_STATIC_DRAW,
        )

        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        position = GL.glGetAttribLocation(self.program, "position")
        GL.glEnableVertexAttribArray(position)
        GL.glVertexAttribPointer(position, 2, GL.GL_FLOAT, GL.GL_FALSE, 0, None)

        return

    def do_bake_shader(self):
        try:
            vertex_shader = compileShader(VERT_SHADER, GL.GL_VERTEX_SHADER)
            fragment_shader = compileShader(self.shader_buffer, GL.GL_FRAGMENT_SHADER)
        except Exception as e:
            raise ShadertoyCompileError(
                f"couldn't compile the provided shader, OpenGL error {e}"
            )
        return compileProgram(vertex_shader, fragment_shader)

    def do_get_timing(self) -> tuple[float, float, float]:
        current_time = GLib.get_monotonic_time() / 1e6
        current_time += 1154 * 8
        delta_time = current_time - self.frame_time
        return current_time, delta_time, 1.0 / delta_time if delta_time > 0 else 0.0

    def do_post_render(self, current_time: float):
        self.frame_time = current_time
        self.frame_count += 1
        return True

    def on_render(self, _, ctx: Gdk.GLContext):
        # clear up for next frame
        GL.glUseProgram(self.program)
        GL.glClearColor(0.0, 0.0, 0.0, 0.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT)

        alloc = self.get_allocation()
        current_time, delta_time, frame_rate = self.do_get_timing()

        # setup the uniforms
        GL.glUniform3f(
            GL.glGetUniformLocation(self.program, "iResolution"),
            alloc.width,
            alloc.height,
            1.0,
        )
        GL.glUniform1f(
            GL.glGetUniformLocation(self.program, "iTime"),
            current_time - self.start_time,
        )
        GL.glUniform1i(
            GL.glGetUniformLocation(self.program, "iFrame"), self.frame_count
        )
        GL.glUniform1f(GL.glGetUniformLocation(self.program, "iTimeDelta"), delta_time)
        GL.glUniform1f(GL.glGetUniformLocation(self.program, "iFrameRate"), frame_rate)

        # update the iMouse uniform (assume mouse position is stored)
        mouse_pos = cast(tuple[int, int], self.get_pointer())
        GL.glUniform4f(
            GL.glGetUniformLocation(self.program, "iMouse"),
            mouse_pos[0],
            alloc.height - mouse_pos[1],
            0,
            0,
        )

        for uname, ubaker in self.unifroms_map.items():
            GL.glUniform1f(GL.glGetUniformLocation(self.program, uname), ubaker())

        # throw a paint quad
        GL.glBindVertexArray(self.vao)
        GL.glDrawArrays(GL.GL_TRIANGLE_STRIP, 0, 4)

        return self.do_post_render(current_time)

    def on_glarea_resize(self, area, width, height):
        GL.glViewport(0, 0, width, height)

    def on_tick(self, _, frame_clock: Gdk.FrameClock):
        self.queue_draw()
        return True


shader_toy_input = """
/**

    License: Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported License

    Corne Keyboard Test Shader
    11/26/2024  @byt3_m3chanic

    Got this tiny Corne knock-off type keyboard from Amazon - 36 key
    So this is me trying to code a shader, and memorize the key
    combos for the special/math chars.

    see keyboard here:
    https://bsky.app/profile/byt3m3chanic.bsky.social/post/3lbsqbatwjc2q

*/

#define R           iResolution
#define T           iTime
#define M           iMouse

#define PI         3.14159265359
#define PI2        6.28318530718

mat2 rot(float a) {return mat2(cos(a),sin(a),-sin(a),cos(a));}
vec3 hue(float t, float f) { return f+f*cos(PI2*t*(vec3(1,.75,.75)+vec3(.96,.57,.12)));}
float hash21(vec2 a) {return fract(sin(dot(a,vec2(27.69,32.58)))*43758.53);}
float box(vec2 p, vec2 b) {vec2 d = abs(p)-b; return length(max(d,0.)) + min(max(d.x,d.y),0.);}
mat2 r90;
vec2 pattern(vec2 p, float sc) {
    vec2 uv = p;
    vec2 id = floor(p*sc);
          p = fract(p*sc)-.5;

    float rnd = hash21(id);

    // turn tiles
    if(rnd>.5) p *= r90;
    rnd=fract(rnd*32.54);
    if(rnd>.4) p *= r90;
    if(rnd>.8) p *= r90;

    // randomize hash for type
    rnd=fract(rnd*47.13);

    float tk = .075;
    // kind of messy and long winded
    float d = box(p-vec2(.6,.7),vec2(.25,.75))-.15;
    float l = box(p-vec2(.7,.5),vec2(.75,.15))-.15;
    float b = box(p+vec2(0,.7),vec2(.05,.25))-.15;
    float r = box(p+vec2(.6,0),vec2(.15,.05))-.15;
    d = abs(d)-tk;

    if(rnd>.92) {
        d = box(p-vec2(-.6,.5),vec2(.25,.15))-.15;
        l = box(p-vec2(.6,.6),vec2(.25))-.15;
        b = box(p+vec2(.6,.6),vec2(.25))-.15;
        r = box(p-vec2(.6,-.6),vec2(.25))-.15;
        d = abs(d)-tk;

    } else if(rnd>.6) {
        d = length(p.x-.2)-tk;
        l = box(p-vec2(-.6,.5),vec2(.25,.15))-.15;
        b = box(p+vec2(.6,.6),vec2(.25))-.15;
        r = box(p-vec2(.3,0),vec2(.25,.05))-.15;
    }

    l = abs(l)-tk; b = abs(b)-tk; r = abs(r)-tk;

    float e = min(d,min(l,min(b,r)));

    if(rnd>.6) {
        r = max(r,-box(p-vec2(.2,.2),vec2(tk*1.3)));
        d = max(d,-box(p+vec2(-.2,.2),vec2(tk*1.3)));
    } else {
        l = max(l,-box(p-vec2(.2,.2),vec2(tk*1.3)));
    }

    d = min(d,min(l,min(b,r)));

    return vec2(d,e);
}
void mainImage( out vec4 O, in vec2 F )
{
    vec3 C = vec3(.0);
    vec2 uv = (2.*F-R.xy)/max(R.x,R.y);
    r90 = rot(1.5707);

    uv *= rot(T*.095);
    //@Shane
    uv = vec2(log(length(uv)), atan(uv.y, uv.x)*6./PI2);
    // Original.
    //uv = vec2(log(length(uv)), atan(uv.y, uv.x))*8./6.2831853;

    float scale = 8.;
    for(float i=0.;i<4.;i++){
        float ff=(i*.05)+.2;

        uv.x+=T*ff;

        float px = fwidth(uv.x*scale);
        vec2 d = pattern(uv,scale);
        vec3 clr = hue(sin(uv.x+(i*8.))*.2+.4,(.5+i)*.15);
        C = mix(C,vec3(.001),smoothstep(px,-px,d.y-.04));
        C = mix(C,clr,smoothstep(px,-px,d.x));
        scale *=.5;
    }

    // Output to screen
    C = pow(C,vec3(.4545));
    O = vec4(C,1.0);
}

"""


class ShadertoyCtrl(Box):
    def bake_scale(self, **kwargs) -> Scale:
        return Scale(draw_value=True, digits=8, **kwargs)

    def bake_label(self, **kwargs) -> Label:
        return Label(h_align="start", v_align="start", **kwargs)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.lightness_scale = self.bake_scale(value=1.0)
        self.colr_scale = self.bake_scale(value=0.9)
        self.colg_scale = self.bake_scale(value=0.85)
        self.colb_scale = self.bake_scale(value=0.8)
        self.mouse_strength_scale = self.bake_scale(value=0.5)
        self.mouse_size_scale = self.bake_scale(value=0.1)
        self.scale_scale = self.bake_scale(value=0.5)
        self.dust_opacity_scale = self.bake_scale(value=0.8)

        self.children = [
            self.bake_label(label="lightness"),
            self.lightness_scale,
            self.bake_label(label="Red Color Channel"),
            self.colr_scale,
            self.bake_label(label="Green Color Channel"),
            self.colg_scale,
            self.bake_label(label="Blue Color Channel"),
            self.colb_scale,
            self.bake_label(label="Mouse Strength"),
            self.mouse_strength_scale,
            self.bake_label(label="Mouse Size"),
            self.mouse_size_scale,
            self.bake_label(label="Scale"),
            self.scale_scale,
            self.bake_label(label="Dust Opacity"),
            self.dust_opacity_scale,
        ]


sdctrl = ShadertoyCtrl(orientation="v")


def inverter(scale: Scale):
    return lambda: scale.max_value - scale.value


shader_toy = Shadertoy(
    shader_buffer=shader_toy_input,
    unifroms_map={
        "u_lightness": inverter(sdctrl.lightness_scale),
        "u_colr": inverter(sdctrl.colr_scale),
        "u_colg": inverter(sdctrl.colg_scale),
        "u_colb": inverter(sdctrl.colb_scale),
        "u_mouse_strength": inverter(sdctrl.mouse_strength_scale),
        "u_mouse_size": inverter(sdctrl.mouse_size_scale),
        "u_scale": inverter(sdctrl.scale_scale),
        "u_dust_opacity": inverter(sdctrl.dust_opacity_scale),
    },
    h_expand=True,
    v_expand=True,
)

app = Application(
    "shader-demo",
    Window(child=sdctrl),
    WaylandWindow(
        anchor="left right top bottom",
        layer="background",
        child=Box(
            spacing=8,
            orientation="v",
            children=[shader_toy],
        ),
        pass_through=True,
        size=(1366, 768),
        on_destroy=Gtk.main_quit,
    ),
)
app.run()