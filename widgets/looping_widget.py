import os

import imgui
import numpy as np
import torch
try:
    import cPickle as pickle
except ModuleNotFoundError:
    import pickle

import dnnlib
from utils.gui_utils import imgui_utils
from widgets import osc_menu
from widgets.browse_widget import BrowseWidget



def slerp(t, v0, v1, DOT_THRESHOLD=0.9995):
    '''
    Spherical linear vizpolation
    Args:
        t (float/np.ndarray): Float value between 0.0 and 1.0
        v0 (np.ndarray): Starting vector
        v1 (np.ndarray): Final vector
        DOT_THRESHOLD (float): Threshold for considering the two vectors as
                               colineal. Not recommended to alter this.
    Returns:
        v2 (np.ndarray): vizpolation vector between v0 and v1
    '''
    v0 = v0.cpu().detach().numpy()
    v1 = v1.cpu().detach().numpy()
    # Copy the vectors to reuse them later
    v0_copy = np.copy(v0)
    v1_copy = np.copy(v1)
    # Normalize the vectors to get the directions and angles
    v0 = v0 / np.linalg.norm(v0)
    v1 = v1 / np.linalg.norm(v1)
    # Dot product with the normalized vectors (can't use np.dot in W)
    dot = np.sum(v0 * v1)
    # If absolute value of dot product is almost 1, vectors are ~colineal, so use lerp
    if np.abs(dot) > DOT_THRESHOLD:
        return torch.from_numpy(v0_copy + (v1_copy - v0_copy) * t)
    # Calculate initial angle between v0 and v1
    theta_0 = np.arccos(dot)
    sin_theta_0 = np.sin(theta_0)
    # Angle at timestep t
    theta_t = theta_0 * t
    sin_theta_t = np.sin(theta_t)
    # Finish the slerp algorithm
    s0 = np.sin(theta_0 - theta_t) / sin_theta_0
    s1 = sin_theta_t / sin_theta_0
    v2 = s0 * v0_copy + s1 * v1_copy
    return torch.from_numpy(v2)



labels = ["Seed", "Vector", "Keyframe"]


class LoopingWidget:
    def __init__(self, viz):
        self.params = dnnlib.EasyDict(num_keyframes=6, mode=True, anim=False, index=0, looptime=4)
        self.use_osc = dnnlib.EasyDict(zip(self.params.keys(), [False] * len(self.params)))
        self.step_y = 100
        self.viz = viz
        self.keyframes = torch.randn(self.params.num_keyframes, 512)
        self.alpha = 0
        self.speed = 0
        self.expand_vec = False
        self.seeds = [[i, 0] for i in range(self.params.num_keyframes)]
        self.modes = [0] * self.params.num_keyframes
        self.project = [True]*self.params.num_keyframes
        self.paths = [""] * self.params.num_keyframes
        self._pinned_bufs = dict()
        self._device = torch.device('cuda')
        self.halt_update = 0
        self.perfect_loop = False
        self.looping_snaps = [{} for _ in range(self.params.num_keyframes)]
        self.file_dialogs = [BrowseWidget(viz, f"Browse##vec{i}", os.path.abspath(os.getcwd()), ["*",".pth", ".pt"], width=self.viz.app.button_w, multiple=False, traverse_folders=False) for i in range(self.params.num_keyframes)]
        self.open_keyframes = False
        self.open_file_dialog = False




        funcs = dict(zip(["anim", "num_keyframes", "looptime", "index", "mode"], [self.osc_handler(param) for param in
                                                                                         ["anim", "num_keyframes", "looptime", "index", "mode"]]))

        funcs["alpha"] = self.alpha_handler()

        self.osc_menu = osc_menu.OscMenu(self.viz, funcs, None,
                                         label="##LoopingOSC")


    def alpha_handler(self):
        def func(address, *args):
            try:
                assert (type(args[-1]) is type(self.alpha)), f"OSC Message and Parameter type must align [OSC] {type(args[-1])} != [Param] {type(self.alpha)}"
                self.alpha = args[-1]
                print(self.alpha, args[-1])
                self.update_alpha()

            except Exception as e:
                self.viz.print_error(e)
        return func
    def osc_handler(self, param):
        def func(address, *args):
            try:
                assert (type(args[-1]) is type(self.params[
                                                   param])), f"OSC Message and Parameter type must align [OSC] {type(args[-1])} != [Param] {type(self.params[param])}"
                self.use_osc[param] = True
                self.params[param] = args[-1]
                print(self.params[param], args[-1])
            except Exception as e:
                self.viz.print_error(e)

        return func

    #Restructure code to make super class that has save and load
    def save(self, path):
        with open(path, "wb") as f:
            pickle.dump(self.get_params(), f)

    def load(self, path):
        with open(path, "rb") as f:
            self.set_params(pickle.load(f))




    def get_params(self):
        return self.params.num_keyframes, self.keyframes, self.alpha, self.params.index, self.params.mode, self.params.anim, self.params.looptime,\
               self.expand_vec,self.seeds, self.modes, self.project, self.paths

    def set_params(self, params):
        self.params.num_keyframes, self.keyframes, self.alpha, self.params.index, self.params.mode, self.params.anim, self.params.looptime, self.expand_vec,self.seeds, self.modes, self.project, self.paths = params

    def drag(self,idx, dx, dy):
        viz = self.viz
        self.seeds[idx][0] += dx / viz.app.font_size * 4e-2
        self.seeds[idx][1] += dy / viz.app.font_size * 4e-2

    def _get_pinned_buf(self, ref):
        key = (tuple(ref.shape), ref.dtype)
        buf = self._pinned_bufs.get(key, None)
        if buf is None:
            buf = torch.empty(ref.shape, dtype=ref.dtype).pin_memory()
            self._pinned_bufs[key] = buf
        return buf

    def to_device(self, buf):
        return self._get_pinned_buf(buf).copy_(buf).to(self._device)

    def to_cpu(self, buf):
        return self._get_pinned_buf(buf).copy_(buf).clone()

    def update_alpha(self):
        step_size = 0
        if self.params.mode:
            if not(self.viz.app._fps_limit is None)and self.params.looptime!=0:
                step_size = (self.params.num_keyframes / self.viz.app._fps_limit)/self.params.looptime
        else:
            step_size = 0.01 * self.speed
        self.alpha += step_size
        if self.alpha >= 1:
            if self.halt_update < 0:
                self.params.index = int(self.params.index+self.alpha)%self.params.num_keyframes
                self.alpha = 0
                if self.params.index == 0 and self.perfect_loop:
                    self.params.anim = False
            self.halt_update = 10
        if step_size < 0:
            if self.alpha <= 0:
                if self.halt_update < 0:
                    self.params.index = self.params.index+self.alpha
                    if self.params.index <= 0:
                        self.params.index += self.params.num_keyframes
                    self.params.index = int(self.params.index %self.params.num_keyframes)
                    self.alpha = 1
                    if self.params.index == 0 and self.perfect_loop:
                        self.params.anim = False
                self.halt_update = 10


        self.halt_update -= 1


    @imgui_utils.scoped_by_object_id
    def key_frame_vizface(self, idx):
        label = labels[self.modes[idx]]
        if imgui_utils.button(f"{label}##{idx}", width=(self.viz.app.font_size*len(label))/2):
            self.modes[idx] = (self.modes[idx] + 1) % len(labels) if self.looping_snaps[idx] != {} else (self.modes[idx] + 1) % (len(labels)-1)
        imgui.same_line()
        _clicked, self.project[idx] = imgui.checkbox(f'Project##loop{idx}', self.project[idx])
        imgui.same_line()
        imgui.text("|")
        imgui.same_line()
        if self.modes[idx]==0:
            self.seed_viz(idx)
        elif self.modes[idx]==1:
            self.vec_viz(idx)
        elif self.modes[idx]==2:
            imgui.text("Not Implemented")

    def open_vec(self, idx):
        try:
            vec = torch.load(self.paths[idx]).squeeze()
            assert vec.shape == self.keyframes[idx].shape, f"The Tensor you are loading has a different shape, Loaded Shape {vec.shape} != Target Shape {self.keyframes[idx].shape}"
            self.keyframes[idx] = vec
        except Exception as e:
            print(e)

    def vec_viz(self, idx):
        viz = self.viz
        changed, self.paths[idx] = imgui_utils.input_text(f"##vec_path_loop{idx}", self.paths[idx], 256,
                                                            imgui.INPUT_TEXT_CHARS_NO_BLANK,
                                                            width=viz.app.font_size*7, help_text="filepath")
        imgui.same_line()
        _clicked, path = self.file_dialogs[idx]()
        if _clicked:
            self.paths[idx] = path
        imgui.same_line()
        if imgui_utils.button(f"Load Vec##loop_{idx}", viz.app.button_w):
            self.open_vec(idx)
        imgui.same_line()
        if imgui_utils.button(f"Snap##{idx}", viz.app.button_w):
            snapped = self.snap()
            print("snapped", snapped, "-----------------------")

            if not(snapped is None):
                if snapped["mode"] == 0:
                    print("SEED")
                    self.seeds[idx] = snapped["snap"]
                    self.modes[idx] = snapped["mode"]
                elif snapped["mode"] == 1:
                    print("VECTOR")
                    self.keyframes[idx] = snapped["snap"]
                    self.modes[idx] = snapped["mode"]
                elif snapped["mode"] == 2:
                    print("getting LOOP")
                    self.looping_snaps[idx] = snapped["snap"]
                    self.modes[idx] = snapped["mode"]
                    print(self.looping_snaps[idx])
                    print(self.modes[idx])

        imgui.same_line()
        if imgui_utils.button(f"Randomize##vecmode{idx}", width=viz.app.button_w):
            self.keyframes[idx] = torch.randn(self.keyframes[idx].shape)


    @imgui_utils.scoped_by_object_id
    def seed_viz(self, idx):
        update_vec = False
        viz = self.viz
        seed = round(self.seeds[idx][0]) + round(self.seeds[idx][1]) * self.step_y
        with imgui_utils.item_width(viz.app.font_size * 8):
            _changed, seed = imgui.input_int(f"##loopseed{idx})", seed)
        if _changed:
            self.seeds[idx][0] = seed
            self.seeds[idx][1] = 0
        imgui.same_line()
        frac_x = self.seeds[idx][0] - round(self.seeds[idx][0])
        frac_y = self.seeds[idx][1] - round(self.seeds[idx][1])
        with imgui_utils.item_width(viz.app.font_size * 5):
            _changed, (new_frac_x, new_frac_y) = imgui.input_float2(f'##loopfrac{idx}', frac_x, frac_y, format='%+.2f',
                                                                    flags=imgui.INPUT_TEXT_ENTER_RETURNS_TRUE)
        if _changed:
            self.seeds[idx][0] += new_frac_x - frac_x
            self.seeds[idx][1] += new_frac_y - frac_y

        imgui.same_line()
        _clicked, dragging, dx, dy = imgui_utils.drag_button(f'Drag##loopdrag{idx}', width=viz.app.button_w)
        if dragging:
            self.drag(idx,dx, dy)

        imgui.same_line()
        if imgui_utils.button(f"Snap##seed{idx}", viz.app.button_w):
            snapped = self.snap()
            print("snapped", snapped, "-----------------------")

            if not(snapped is None):
                if snapped["mode"] == 0:
                    print("SEED")
                    self.seeds[idx] = snapped["snap"]
                    self.modes[idx] = snapped["mode"]
                elif snapped["mode"] == 1:
                    print("VECTOR")
                    self.keyframes[idx] = snapped["snap"]
                    self.modes[idx] = snapped["mode"]
                elif snapped["mode"] == 2:
                    print("getting LOOP")
                    self.looping_snaps[idx] = snapped["snap"]
                    self.modes[idx] = snapped["mode"]
                    print(self.looping_snaps[idx])
                    print(self.modes[idx])

    @imgui_utils.scoped_by_object_id
    def __call__(self, show=True):
        viz = self.viz
        # viz.args.looping = self.params.anim

        if show:
            _clicked, self.params.anim = imgui.checkbox('Loop', self.params.anim)
            with imgui_utils.item_width(viz.app.font_size*5):
                changed, new_keyframes = imgui.input_int("# of Keyframes", self.params.num_keyframes)
            if changed and new_keyframes > 0:
                vecs= torch.randn(new_keyframes,512)
                vecs[:min(new_keyframes,self.params.num_keyframes)] = self.keyframes[:min(new_keyframes,self.params.num_keyframes)]
                self.keyframes = vecs
                if not self.use_osc:
                    self.params.index = min(self.params.num_keyframes-2, self.params.index)
                seeds = [dnnlib.EasyDict(x=i,y=0) for i in range(new_keyframes)]
                seeds[:min(new_keyframes, self.params.num_keyframes)] = self.seeds[:min(new_keyframes, self.params.num_keyframes)]
                self.seeds = seeds
                paths = [""]*new_keyframes
                paths[:min(new_keyframes, self.params.num_keyframes)] = self.paths[:min(new_keyframes, self.params.num_keyframes)]
                self.paths = paths
                modes = [False]*new_keyframes
                modes[:min(new_keyframes, self.params.num_keyframes)] = self.modes[:min(new_keyframes, self.params.num_keyframes)]
                self.modes = modes
                project = [True]*new_keyframes
                project[:min(new_keyframes, self.params.num_keyframes)] = self.project[:min(new_keyframes, self.params.num_keyframes)]
                self.project = project
                self.params.num_keyframes = new_keyframes
                looping_snaps = [{} for _ in range(new_keyframes)]
                looping_snaps[:min(new_keyframes, self.params.num_keyframes)] = self.looping_snaps[
                                                                        :min(new_keyframes, self.params.num_keyframes)]
                self.looping_snaps = looping_snaps

                file_dialogs = [BrowseWidget(viz, f"Vector##vec{i}", os.path.abspath(os.getcwd()), ["*",".pth", ".pt"], width=self.viz.app.button_w, multiple=False, traverse_folders=False) for i in range(new_keyframes)]
                file_dialogs[:min(new_keyframes, self.params.num_keyframes)] = self.file_dialogs[:min(new_keyframes, self.params.num_keyframes)]
                self.file_dialogs = file_dialogs


            imgui.same_line()
            label = "Time" if self.params.mode else "Speed"
            if imgui_utils.button(f'{label}##loopmode', width=viz.app.button_w,enabled=True):
                self.params.mode = not self.params.mode
            imgui.same_line()
            if self.params.mode:
                imgui.same_line()
                with imgui_utils.item_width(viz.app.font_size * 5):
                    changed, self.params.looptime = imgui.input_int("Time to loop", self.params.looptime)
            else:
                with imgui_utils.item_width(viz.app.button_w * 2 - viz.app.spacing * 2):
                    changed, speed = imgui.slider_float('##speed', self.speed, -5, 5, format='Speed %.3f',
                                                        power=3)
                    if changed:
                        self.speed = speed
            imgui.same_line()
            if imgui_utils.button("KeyFrames", width=viz.app.button_w):
                self.open_keyframes = True
            if self.open_keyframes:
                collapsed, self.open_keyframes = imgui.begin("KeyFrames", closable=True, flags=imgui.WINDOW_ALWAYS_AUTO_RESIZE|imgui.WINDOW_NO_COLLAPSE)
                if collapsed:
                    for i in range(self.params.num_keyframes):
                        self.key_frame_vizface(i)

                # check if any file dialogs are open
                open_dialog = False
                for file_dialog in self.file_dialogs:
                    if file_dialog.open:
                        open_dialog = True
                        break
                if self.open_file_dialog == True and not open_dialog:
                    self.open_file_dialog = False
                    imgui.set_window_focus()

                self.open_file_dialog = open_dialog
                # check if current window focussed if not close it unless a file dialog is open
                if not imgui.is_window_focused() and not self.open_file_dialog:
                    self.open_keyframes = False
                imgui.end()
            imgui.same_line()
            with imgui_utils.item_width(viz.app.font_size*5):
                changed, idx = imgui.input_int("index", self.params.index+1)
                if changed:
                    self.params.index = int((idx-1) % self.params.num_keyframes)
            imgui.same_line()
            with imgui_utils.item_width(viz.app.font_size*5):
                changed, self.alpha = imgui.slider_float("alpha", self.alpha, 0, 1)

            _, self.perfect_loop = imgui.checkbox("Perfect Loop", self.perfect_loop)

            if self.params.anim:
                self.update_alpha()
                viz.args.alpha = self.alpha
                viz.args.looping_index = self.params.index
                viz.args.mode = "loop"
                l_list = []
                for i, mode in enumerate(self.modes):
                    if mode == 0:
                        l_list.append({"mode": "seed", "latent": self.seeds[i], "project": self.project[i]})
                    elif mode == 1:
                        l_list.append({"mode": "vec", "latent": self.keyframes[i], "project": self.project[i]})
                    elif mode == 2:
                        print("adding loop", self.looping_snaps[i])
                        l_list.append({"mode": "loop", "looping_list": self.looping_snaps[i]["looping_list"], "looping_index": self.looping_snaps[i]["index"], "alpha": self.looping_snaps[i]["alpha"]})
                viz.args.looping_list = l_list

        self.osc_menu()

    def snap(self):
        return self.viz.result.get("snap", None)











