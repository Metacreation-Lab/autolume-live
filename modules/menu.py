# Copyright (c) 2021, NVIDIA CORPORATION & AFFILIATES.  All rights reserved.
#
# NVIDIA CORPORATION and its licensors retain all intellectual property
# and proprietary rights in and to this software, related documentation
# and any modifications thereto.  Any use, reproduction, disclosure or
# distribution of this software and related documentation without an express
# license agreement from NVIDIA CORPORATION is strictly prohibited.

import click
import cv2
import imgui
import numpy as np

from assets import RED
from utils.gui_utils import imgui_window, gl_utils
from utils.gui_utils import imgui_utils
from modules.pca_module import PCA_Module
from modules.training_module import TrainingModule
from modules.compress_module import CompressModule
from modules.network_surgery import SurgeryModule
from modules.projection_module import ProjectionModule
from modules.network_mixing import MixingModule

from modules.super_res_module import SuperResModule
#----------------------------------------------------------------------------
class Menu:
    def __init__(self, app):
        self.app = app
        self.pca = PCA_Module(self)
        self.training = TrainingModule(self)
        self.compress = CompressModule(self)
        # self.network_surgery = SurgeryModule(self)
        self.projection = ProjectionModule(self)
        self.super_res = SuperResModule(self)
        self.mixing_module = MixingModule(self)
        self.logo = cv2.imread("assets/Autolume-logo.png", cv2.IMREAD_UNCHANGED)
        self.logo_texture = gl_utils.Texture(image=self.logo, width=self.logo.shape[1], height=self.logo.shape[0], channels=self.logo.shape[2])

        self.metacreation = cv2.imread("assets/metalogo.png", cv2.IMREAD_UNCHANGED)
        self.metacreation_texture = gl_utils.Texture(image=self.metacreation, width=self.metacreation.shape[1], height=self.metacreation.shape[0], channels=self.metacreation.shape[2])

    def __call__(self):
        imgui.set_next_window_position(0, 0)
        imgui.set_next_window_size(self.app.content_width, self.logo.shape[0] * 1.5)
        imgui.begin('##Menu', closable=False, flags=(imgui.WINDOW_NO_RESIZE | imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_BRING_TO_FRONT_ON_FOCUS|imgui.WINDOW_NO_TITLE_BAR))
        # set red background
        imgui.get_window_draw_list().add_rect_filled(0, 0, self.app.content_width, self.logo.shape[0] * 1.5, imgui.get_color_u32_rgba(*RED))
        imgui.image(self.logo_texture.gl_id, self.logo.shape[1], self.logo.shape[0])
        imgui.same_line(self.app.content_width - (self.metacreation.shape[1] + self.app.spacing))
        imgui.image(self.metacreation_texture.gl_id, self.metacreation.shape[1], self.metacreation.shape[0])
        imgui.end()
        # Make train and compress buttons call function as subprocess to avoid blocking
        # Begin control pane.
        imgui.set_next_window_position(0, self.logo.shape[0] * 1.5)
        imgui.set_next_window_size(self.app.content_width//4, (self.app.content_height * 4) //5)
        imgui.begin('Train##Menu', closable=False, flags=(imgui.WINDOW_NO_RESIZE | imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_BRING_TO_FRONT_ON_FOCUS))
        imgui.text("Train")
        self.training()
        imgui.end()

        imgui.set_next_window_position(self.app.content_width // 4, self.logo.shape[0] * 1.5)
        imgui.set_next_window_size(self.app.content_width // 4, (self.app.content_height * 4) // 5)
        imgui.begin('Projection##Menu', closable=False, flags=(imgui.WINDOW_NO_RESIZE | imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_BRING_TO_FRONT_ON_FOCUS))
        imgui.text("Projection")
        # self.compress()
        self.projection()
        imgui.end()

        imgui.set_next_window_position((2 * self.app.content_width)// 4, self.logo.shape[0] * 1.5)
        imgui.set_next_window_size(self.app.content_width // 4, (self.app.content_height * 4) // 5)
        imgui.begin('GANSPACE##Menu', closable=False, flags=(imgui.WINDOW_NO_RESIZE | imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_BRING_TO_FRONT_ON_FOCUS))
        imgui.text("GANSPACE")
        self.pca()
        imgui.end()

        imgui.set_next_window_position((3 * self.app.content_width)// 4, self.logo.shape[0] * 1.5)
        imgui.set_next_window_size(self.app.content_width // 3, (self.app.content_height * 4) // 5)
        imgui.begin('Super-res##Menu', closable=False, flags=(imgui.WINDOW_NO_RESIZE | imgui.WINDOW_NO_MOVE | imgui.WINDOW_NO_BRING_TO_FRONT_ON_FOCUS))
        imgui.text("Super-res")
        self.super_res()
        imgui.end()

        imgui.set_next_window_position(0, (self.app.content_height * 3) // 4)
        imgui.set_next_window_size(self.app.content_width // 2, (self.app.content_height * 3) // 4)
        imgui.begin('Surgery##Menu', closable=False, flags=(imgui.WINDOW_NO_RESIZE | imgui.WINDOW_NO_MOVE))
        imgui.text("Network Surgery")
        self.mixing_module()
        imgui.end()

        imgui.set_next_window_position(self.app.content_width//2,(self.app.content_height * 3) // 4)
        imgui.set_next_window_size(self.app.content_width//2, (self.app.content_height * 3) // 4)
        imgui.begin('Render##Menu', closable=False, flags=(imgui.WINDOW_NO_RESIZE | imgui.WINDOW_NO_MOVE))
        imgui.text("Renderer")
        if imgui_utils.button("START", width=self.app.button_w):
            self.app.start_renderer()


        imgui.end()



