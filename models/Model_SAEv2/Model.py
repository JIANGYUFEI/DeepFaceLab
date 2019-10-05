from functools import partial

import numpy as np

import mathlib
from facelib import FaceType
from interact import interact as io
from models import ModelBase
from nnlib import nnlib
from samplelib import *


#SAE - Styled AutoEncoder
class SAEv2Model(ModelBase):

    #override
    def onInitializeOptions(self, is_first_run, ask_override):
        yn_str = {True:'y',False:'n'}

        default_resolution = 128
        default_archi = 'df'
        default_face_type = 'f'
        default_learn_mask = True

        if is_first_run:
            resolution = io.input_int("Resolution ( 64-256 ?:help skip:128) : ", default_resolution, help_message="More resolution requires more VRAM and time to train. Value will be adjusted to multiple of 16.")
            resolution = np.clip (resolution, 64, 256)
            while np.modf(resolution / 16)[0] != 0.0:
                resolution -= 1
            self.options['resolution'] = resolution

            self.options['face_type'] = io.input_str ("Half, mid full, or full face? (h/mf/f, ?:help skip:f) : ", default_face_type, ['h','mf','f'], help_message="Half face has better resolution, but covers less area of cheeks. Mid face is 30% wider than half face.").lower()
            self.options['learn_mask'] = io.input_bool ( f"Learn mask? (y/n, ?:help skip:{yn_str[default_learn_mask]} ) : " , default_learn_mask, help_message="Learning mask can help model to recognize face directions. Learn without mask can reduce model size, in this case converter forced to use 'not predicted mask' that is not smooth as predicted. Model with style values can be learned without mask and produce same quality result.")
        else:
            self.options['resolution'] = self.options.get('resolution', default_resolution)
            self.options['face_type'] = self.options.get('face_type', default_face_type)
            self.options['learn_mask'] = self.options.get('learn_mask', default_learn_mask)

        if (is_first_run or ask_override) and 'tensorflow' in self.device_config.backend:
            def_optimizer_mode = self.options.get('optimizer_mode', 1)
            self.options['optimizer_mode'] = io.input_int ("Optimizer mode? ( 1,2,3 ?:help skip:%d) : " % (def_optimizer_mode), def_optimizer_mode, help_message="1 - no changes. 2 - allows you to train x2 bigger network consuming RAM. 3 - allows you to train x3 bigger network consuming huge amount of RAM and slower, depends on CPU power.")
        else:
            self.options['optimizer_mode'] = self.options.get('optimizer_mode', 1)

        if is_first_run:
            self.options['archi'] = io.input_str ("AE architecture (df, liae ?:help skip:%s) : " % (default_archi) , default_archi, ['df','liae'], help_message="'df' keeps faces more natural. 'liae' can fix overly different face shapes.").lower() #-s version is slower, but has decreased change to collapse.
        else:
            self.options['archi'] = self.options.get('archi', default_archi)

        default_ae_dims = 256 if 'liae' in self.options['archi'] else 512
        default_e_ch_dims = 21
        default_d_ch_dims = default_e_ch_dims
        def_ca_weights = False

        if is_first_run:
            self.options['ae_dims'] = np.clip ( io.input_int("AutoEncoder dims (32-1024 ?:help skip:%d) : " % (default_ae_dims) , default_ae_dims, help_message="All face information will packed to AE dims. If amount of AE dims are not enough, then for example closed eyes will not be recognized. More dims are better, but require more VRAM. You can fine-tune model size to fit your GPU." ), 32, 1024 )
            self.options['e_ch_dims'] = np.clip ( io.input_int("Encoder dims per channel (21-85 ?:help skip:%d) : " % (default_e_ch_dims) , default_e_ch_dims, help_message="More encoder dims help to recognize more facial features, but require more VRAM. You can fine-tune model size to fit your GPU." ), 21, 85 )
            default_d_ch_dims = self.options['e_ch_dims'] 
            self.options['d_ch_dims'] = np.clip ( io.input_int("Decoder dims per channel (10-85 ?:help skip:%d) : " % (default_d_ch_dims) , default_d_ch_dims, help_message="More decoder dims help to get better details, but require more VRAM. You can fine-tune model size to fit your GPU." ), 10, 85 )
            self.options['ca_weights'] = io.input_bool (f"Use CA weights? (y/n, ?:help skip:{yn_str[def_ca_weights]} ) : ", def_ca_weights, help_message="Initialize network with 'Convolution Aware' weights. This may help to achieve a higher accuracy model, but consumes a time at first run.")
        else:
            self.options['ae_dims'] = self.options.get('ae_dims', default_ae_dims)
            self.options['e_ch_dims'] = self.options.get('e_ch_dims', default_e_ch_dims)
            self.options['d_ch_dims'] = self.options.get('d_ch_dims', default_d_ch_dims)
            self.options['ca_weights'] = self.options.get('ca_weights', def_ca_weights)

        default_face_style_power = 0.0
        default_bg_style_power = 0.0
        if is_first_run or ask_override:
            def_pixel_loss = self.options.get('pixel_loss', False)
            self.options['pixel_loss'] = io.input_bool (f"Use pixel loss? (y/n, ?:help skip:{yn_str[def_pixel_loss]} ) : ", def_pixel_loss, help_message="Pixel loss may help to enhance fine details and stabilize face color. Use it only if quality does not improve over time. Enabling this option too early increases the chance of model collapse.")

            default_face_style_power = default_face_style_power if is_first_run else self.options.get('face_style_power', default_face_style_power)
            self.options['face_style_power'] = np.clip ( io.input_number("Face style power ( 0.0 .. 100.0 ?:help skip:%.2f) : " % (default_face_style_power), default_face_style_power,
                                                                               help_message="Learn to transfer face style details such as light and color conditions. Warning: Enable it only after 10k iters, when predicted face is clear enough to start learn style. Start from 0.1 value and check history changes. Enabling this option increases the chance of model collapse."), 0.0, 100.0 )

            default_bg_style_power = default_bg_style_power if is_first_run else self.options.get('bg_style_power', default_bg_style_power)
            self.options['bg_style_power'] = np.clip ( io.input_number("Background style power ( 0.0 .. 100.0 ?:help skip:%.2f) : " % (default_bg_style_power), default_bg_style_power,
                                                                               help_message="Learn to transfer image around face. This can make face more like dst. Enabling this option increases the chance of model collapse."), 0.0, 100.0 )

            default_apply_random_ct = False if is_first_run else self.options.get('apply_random_ct', False)
            self.options['apply_random_ct'] = io.input_bool (f"Apply random color transfer to src faceset? (y/n, ?:help skip:{yn_str[default_apply_random_ct]}) : ", default_apply_random_ct, help_message="Increase variativity of src samples by apply LCT color transfer from random dst samples. It is like 'face_style' learning, but more precise color transfer and without risk of model collapse, also it does not require additional GPU resources, but the training time may be longer, due to the src faceset is becoming more diverse.")

            default_true_face_training = False if is_first_run else self.options.get('true_face_training', False)
            self.options['true_face_training'] = io.input_bool (f"Enable 'true face' training? (y/n, ?:help skip:{yn_str[default_true_face_training]}) : ", default_true_face_training, help_message="Result face will be more like src. Enable it only after 100k iters, when face is sharp enough.")


            if nnlib.device.backend != 'plaidML': # todo https://github.com/plaidml/plaidml/issues/301
                default_clipgrad = False if is_first_run else self.options.get('clipgrad', False)
                self.options['clipgrad'] = io.input_bool (f"Enable gradient clipping? (y/n, ?:help skip:{yn_str[default_clipgrad]}) : ", default_clipgrad, help_message="Gradient clipping reduces chance of model collapse, sacrificing speed of training.")
            else:
                self.options['clipgrad'] = False

        else:
            self.options['pixel_loss'] = self.options.get('pixel_loss', False)
            self.options['face_style_power'] = self.options.get('face_style_power', default_face_style_power)
            self.options['bg_style_power'] = self.options.get('bg_style_power', default_bg_style_power)
            self.options['apply_random_ct'] = self.options.get('apply_random_ct', False)
            self.options['clipgrad'] = self.options.get('clipgrad', False)

        if is_first_run:
            self.options['pretrain'] = io.input_bool ("Pretrain the model? (y/n, ?:help skip:n) : ", False, help_message="Pretrain the model with large amount of various faces. This technique may help to train the fake with overly different face shapes and light conditions of src/dst data. Face will be look more like a morphed. To reduce the morph effect, some model files will be initialized but not be updated after pretrain: LIAE: inter_AB.h5 DF: encoder.h5. The longer you pretrain the model the more morphed face will look. After that, save and run the training again.")
        else:
            self.options['pretrain'] = False

    #override
    def onInitialize(self):
        exec(nnlib.import_all(), locals(), globals())
        self.set_vram_batch_requirements({1.5:4,4:8})

        resolution = self.options['resolution']
        learn_mask = self.options['learn_mask']

        ae_dims = self.options['ae_dims']
        e_ch_dims = self.options['e_ch_dims']
        d_ch_dims = self.options['d_ch_dims']
        self.pretrain = self.options['pretrain'] = self.options.get('pretrain', False)
        if not self.pretrain:
            self.options.pop('pretrain')

        bgr_shape = (resolution, resolution, 3)
        mask_shape = (resolution, resolution, 1)

        apply_random_ct = self.options.get('apply_random_ct', False)
        self.true_face_training = self.options.get('true_face_training', False)
        masked_training = True

        class SAEDFModel(object):
            def __init__(self, resolution, ae_dims, e_ch_dims, d_ch_dims, learn_mask):
                super().__init__()
                self.learn_mask = learn_mask

                output_nc = 3
                bgr_shape = (resolution, resolution, output_nc)
                mask_shape = (resolution, resolution, 1)
                lowest_dense_res = resolution // 16
                e_dims = output_nc*e_ch_dims

                def downscale (dim, kernel_size=5, dilation_rate=1):
                    def func(x):
                        return SubpixelDownscaler()(LeakyReLU(0.1)(Conv2D(dim // 4, kernel_size=kernel_size, strides=1, dilation_rate=dilation_rate, padding='same')(x)))
                    return func
                    
                def upscale (dim, size=(2,2)):
                    def func(x):
                        return SubpixelUpscaler(size=size)(LeakyReLU(0.1)(Conv2D(dim * np.prod(size) , kernel_size=3, strides=1, padding='same')(x)))
                    return func

                def enc_flow(e_dims, ae_dims, lowest_dense_res):
                    def func(inp):                        
                        x = downscale(e_dims  , 3, 1 )(inp)
                        x = downscale(e_dims*2, 3, 1 )(x)
                        x = downscale(e_dims*4, 3, 1 )(x)
                        x0 = downscale(e_dims*8, 3, 1 )(x)
                        
                        x = downscale(e_dims  , 5, 1 )(inp)
                        x = downscale(e_dims*2, 5, 1 )(x)
                        x = downscale(e_dims*4, 5, 1 )(x)
                        x1 = downscale(e_dims*8, 5, 1 )(x)
                        
                        x = downscale(e_dims  , 5, 2 )(inp)
                        x = downscale(e_dims*2, 5, 2 )(x)
                        x = downscale(e_dims*4, 5, 2 )(x)
                        x2 = downscale(e_dims*8, 5, 2 )(x)
                        
                        x = downscale(e_dims  , 7, 2 )(inp)
                        x = downscale(e_dims*2, 7, 2 )(x)
                        x = downscale(e_dims*4, 7, 2 )(x)
                        x3 = downscale(e_dims*8, 7, 2 )(x)
                        
                        x = Concatenate()([x0,x1,x2,x3])
                        
                        x = Dense(ae_dims)(Flatten()(x))
                        x = Dense(lowest_dense_res * lowest_dense_res * ae_dims)(x)
                        x = Reshape((lowest_dense_res, lowest_dense_res, ae_dims))(x)
                        x = upscale(ae_dims)(x)
                        return x
                    return func

                def dec_flow(output_nc, d_ch_dims, add_residual_blocks=True):
                    dims = output_nc * d_ch_dims
                    def ResidualBlock(dim):
                        def func(inp):
                            x = Conv2D(dim, kernel_size=3, padding='same')(inp)
                            x = LeakyReLU(0.2)(x)
                            x = Conv2D(dim, kernel_size=3, padding='same')(x)
                            x = Add()([x, inp])
                            x = LeakyReLU(0.2)(x)
                            return x
                        return func
                    """
                    def func(x):
                        x0 = upscale(dims, size=(8,8) )(x)
                        
                        x = upscale(dims*4)(x)

                        if add_residual_blocks:
                            x = ResidualBlock(dims*4)(x)

                        x1 = upscale(dims, size=(4,4) )(x)
                        
                        x = upscale(dims*2)(x)

                        if add_residual_blocks:
                            x = ResidualBlock(dims*2)(x)
                            
                        x2 = upscale(dims, size=(2,2) )(x)

                        x = upscale(dims)(x)

                        if add_residual_blocks:
                            x = ResidualBlock(dims)(x)
                            
                        x = Add()([x0,x1,x2,x])
                        

                        return Conv2D(output_nc, kernel_size=5, padding='same', activation='sigmoid')(x)
                    """    
                    def func(x):
                        
                        x = upscale(dims*8)(x)

                        if add_residual_blocks:
                            x = ResidualBlock(dims*8)(x)

                        x = upscale(dims*4)(x)

                        if add_residual_blocks:
                            x = ResidualBlock(dims*4)(x)

                        x = upscale(dims*2)(x)

                        if add_residual_blocks:
                            x = ResidualBlock(dims*2)(x)

                        return Conv2D(output_nc, kernel_size=5, padding='same', activation='sigmoid')(x)

                    return func

                self.encoder = modelify(enc_flow(e_dims, ae_dims, lowest_dense_res)) ( Input(bgr_shape) )

                sh = K.int_shape( self.encoder.outputs[0] )[1:]
                self.decoder_src = modelify(dec_flow(output_nc, d_ch_dims)) ( Input(sh) )
                self.decoder_dst = modelify(dec_flow(output_nc, d_ch_dims)) ( Input(sh) )

                if learn_mask:
                    self.decoder_srcm = modelify(dec_flow(1, d_ch_dims, add_residual_blocks=False)) ( Input(sh) )
                    self.decoder_dstm = modelify(dec_flow(1, d_ch_dims, add_residual_blocks=False)) ( Input(sh) )

                self.src_dst_trainable_weights = self.encoder.trainable_weights + self.decoder_src.trainable_weights + self.decoder_dst.trainable_weights

                if learn_mask:
                    self.src_dst_mask_trainable_weights = self.encoder.trainable_weights + self.decoder_srcm.trainable_weights + self.decoder_dstm.trainable_weights

                self.warped_src, self.warped_dst = Input(bgr_shape), Input(bgr_shape)
                self.target_src, self.target_dst = Input(bgr_shape), Input(bgr_shape)
                self.target_srcm, self.target_dstm = Input(mask_shape), Input(mask_shape)
                self.src_code, self.dst_code = self.encoder(self.warped_src), self.encoder(self.warped_dst)

                self.pred_src_src = self.decoder_src(self.src_code)
                self.pred_dst_dst = self.decoder_dst(self.dst_code)
                self.pred_src_dst = self.decoder_src(self.dst_code)

                if learn_mask:
                    self.pred_src_srcm = self.decoder_srcm(self.src_code)
                    self.pred_dst_dstm = self.decoder_dstm(self.dst_code)
                    self.pred_src_dstm = self.decoder_srcm(self.dst_code)

            def get_model_filename_list(self, exclude_for_pretrain=False):
                ar = []
                if not exclude_for_pretrain:
                    ar += [ [self.encoder, 'encoder.h5'] ]
                ar += [  [self.decoder_src, 'decoder_src.h5'],
                         [self.decoder_dst, 'decoder_dst.h5']  ]
                if self.learn_mask:
                    ar += [ [self.decoder_srcm, 'decoder_srcm.h5'],
                            [self.decoder_dstm, 'decoder_dstm.h5']  ]
                return ar

        class SAELIAEModel(object):
            def __init__(self, resolution, ae_dims, e_ch_dims, d_ch_dims, learn_mask):
                super().__init__()
                self.learn_mask = learn_mask

                output_nc = 3
                bgr_shape = (resolution, resolution, output_nc)
                mask_shape = (resolution, resolution, 1)

                e_dims = output_nc*e_ch_dims

                lowest_dense_res = resolution // 16
                
                def downscale (dim, kernel_size=5, dilation_rate=1):
                    def func(x):
                        return SubpixelDownscaler()(LeakyReLU(0.1)(Conv2D(dim // 4, kernel_size=kernel_size, strides=1, dilation_rate=dilation_rate, padding='same')(x)))
                    return func
                    
                def upscale (dim):
                    def func(x):
                        return SubpixelUpscaler()(LeakyReLU(0.1)(Conv2D(dim * 4, kernel_size=3, strides=1, padding='same')(x)))
                    return func

                def enc_flow(e_dims):
                    def func(inp):                        
                        x = downscale(e_dims  , 3, 1 )(inp)
                        x = downscale(e_dims*2, 3, 1 )(x)
                        x = downscale(e_dims*4, 3, 1 )(x)
                        x0 = downscale(e_dims*8, 3, 1 )(x)
                        
                        x = downscale(e_dims  , 5, 1 )(inp)
                        x = downscale(e_dims*2, 5, 1 )(x)
                        x = downscale(e_dims*4, 5, 1 )(x)
                        x1 = downscale(e_dims*8, 5, 1 )(x)
                        
                        x = downscale(e_dims  , 5, 2 )(inp)
                        x = downscale(e_dims*2, 5, 2 )(x)
                        x = downscale(e_dims*4, 5, 2 )(x)
                        x2 = downscale(e_dims*8, 5, 2 )(x)
                        
                        x = downscale(e_dims  , 7, 2 )(inp)
                        x = downscale(e_dims*2, 7, 2 )(x)
                        x = downscale(e_dims*4, 7, 2 )(x)
                        x3 = downscale(e_dims*8, 7, 2 )(x)
                        
                        x = Concatenate()([x0,x1,x2,x3])
                        
                        x = Flatten()(x)
                        return x
                    return func

                def inter_flow(lowest_dense_res, ae_dims):
                    def func(x):
                        x = Dense(ae_dims)(x)
                        x = Dense(lowest_dense_res * lowest_dense_res * ae_dims*2)(x)
                        x = Reshape((lowest_dense_res, lowest_dense_res, ae_dims*2))(x)
                        x = upscale(ae_dims*2)(x)
                        return x
                    return func

                def dec_flow(output_nc, d_ch_dims, add_residual_blocks=True):
                    d_dims = output_nc*d_ch_dims
                    def ResidualBlock(dim):
                        def func(inp):
                            x = Conv2D(dim, kernel_size=3, padding='same')(inp)
                            x = LeakyReLU(0.2)(x)
                            x = Conv2D(dim, kernel_size=3, padding='same')(inp)
                            x = Add()([x, inp])
                            x = LeakyReLU(0.2)(x)
                            return x
                        return func

                    def func(x):
                        x = upscale(d_dims*8)(x)

                        if add_residual_blocks:
                            x = ResidualBlock(d_dims*8)(x)
                            
                        x = upscale(d_dims*4)(x)

                        if add_residual_blocks:
                            x = ResidualBlock(d_dims*4)(x)

                        x = upscale(d_dims*2)(x)

                        if add_residual_blocks:
                            x = ResidualBlock(d_dims*2)(x)

                        return Conv2D(output_nc, kernel_size=5, padding='same', activation='sigmoid')(x)
                    return func

                self.encoder = modelify(enc_flow(e_dims)) ( Input(bgr_shape) )

                sh = K.int_shape( self.encoder.outputs[0] )[1:]
                self.inter_B = modelify(inter_flow(lowest_dense_res, ae_dims)) ( Input(sh) )
                self.inter_AB = modelify(inter_flow(lowest_dense_res, ae_dims)) ( Input(sh) )

                sh = np.array(K.int_shape( self.inter_B.outputs[0] )[1:])*(1,1,2)
                self.decoder = modelify(dec_flow(output_nc, d_ch_dims)) ( Input(sh) )

                if learn_mask:
                    self.decoderm = modelify(dec_flow(1, d_ch_dims, add_residual_blocks=False)) ( Input(sh) )

                self.src_dst_trainable_weights = self.encoder.trainable_weights + self.inter_B.trainable_weights + self.inter_AB.trainable_weights + self.decoder.trainable_weights

                if learn_mask:
                    self.src_dst_mask_trainable_weights = self.encoder.trainable_weights + self.inter_B.trainable_weights + self.inter_AB.trainable_weights + self.decoderm.trainable_weights

                self.warped_src, self.warped_dst = Input(bgr_shape), Input(bgr_shape)
                self.target_src, self.target_dst = Input(bgr_shape), Input(bgr_shape)
                self.target_srcm, self.target_dstm = Input(mask_shape), Input(mask_shape)
                
                warped_src_code = self.encoder (self.warped_src)
                self.src_code = warped_src_inter_AB_code = self.inter_AB (warped_src_code)
                src_code = Concatenate()([warped_src_inter_AB_code,warped_src_inter_AB_code])

                warped_dst_code = self.encoder (self.warped_dst)
                self.dst_code = warped_dst_inter_B_code = self.inter_B (warped_dst_code)
                warped_dst_inter_AB_code = self.inter_AB (warped_dst_code)
                dst_code = Concatenate()([warped_dst_inter_B_code,warped_dst_inter_AB_code])

                src_dst_code = Concatenate()([warped_dst_inter_AB_code,warped_dst_inter_AB_code])

                self.pred_src_src = self.decoder(src_code)
                self.pred_dst_dst = self.decoder(dst_code)
                self.pred_src_dst = self.decoder(src_dst_code)

                if learn_mask:
                    self.pred_src_srcm = self.decoderm(src_code)
                    self.pred_dst_dstm = self.decoderm(dst_code)
                    self.pred_src_dstm = self.decoderm(src_dst_code)

            def get_model_filename_list(self, exclude_for_pretrain=False):
                ar = [ [self.encoder, 'encoder.h5'],
                       [self.inter_B, 'inter_B.h5'] ]

                if not exclude_for_pretrain:
                    ar += [ [self.inter_AB, 'inter_AB.h5'] ]

                ar += [  [self.decoder, 'decoder.h5']  ]

                if self.learn_mask:
                    ar += [ [self.decoderm, 'decoderm.h5'] ]

                return ar

        if 'df' in self.options['archi']:
            self.model = SAEDFModel (resolution, ae_dims, e_ch_dims, d_ch_dims, learn_mask)
        elif 'liae' in self.options['archi']:
            self.model = SAELIAEModel (resolution, ae_dims, e_ch_dims, d_ch_dims, learn_mask)
            
        self.opt_dis_model = []
        
        if self.true_face_training:
            def dis_flow(ndf=256):
                def func(x):
                    x, = x
                    
                    code_res = K.int_shape(x)[1]

                    x = Conv2D( ndf, 4, strides=2, padding='valid')( ZeroPadding2D(1)(x) )
                    x = LeakyReLU(0.1)(x)

                    x = Conv2D( ndf*2, 3, strides=2, padding='valid')( ZeroPadding2D(1)(x) )
                    x = LeakyReLU(0.1)(x)
                    
                    if code_res > 8:
                        x = Conv2D( ndf*4, 3, strides=2, padding='valid')( ZeroPadding2D(1)(x) )
                        x = LeakyReLU(0.1)(x)
                        
                    if code_res > 16:
                        x = Conv2D( ndf*8, 3, strides=2, padding='valid')( ZeroPadding2D(1)(x) )
                        x = LeakyReLU(0.1)(x)
                        
                    if code_res > 32:
                        x = Conv2D( ndf*8, 3, strides=2, padding='valid')( ZeroPadding2D(1)(x) )
                        x = LeakyReLU(0.1)(x)

                    return Conv2D( 1, 1, strides=1, padding='valid', activation='sigmoid')(x)
                return func
            
            sh = [ Input( K.int_shape(self.model.src_code)[1:] ) ]
            self.dis = modelify(dis_flow()) (sh)
            
            self.opt_dis_model = [ (self.dis, 'dis.h5') ]

        loaded, not_loaded = [], self.model.get_model_filename_list()+self.opt_dis_model
        if not self.is_first_run():
            loaded, not_loaded = self.load_weights_safe(not_loaded)

        CA_models = []
        if self.options.get('ca_weights', False):
            CA_models += [ model for model, _ in not_loaded ]

        CA_conv_weights_list = []
        for model in CA_models:
            for layer in model.layers:
                if type(layer) == keras.layers.Conv2D:
                    CA_conv_weights_list += [layer.weights[0]] #- is Conv2D kernel_weights

        if len(CA_conv_weights_list) != 0:
            CAInitializerMP ( CA_conv_weights_list )

        target_srcm = gaussian_blur( max(1, resolution // 32) )(self.model.target_srcm)
        target_dstm = gaussian_blur( max(1, resolution // 32) )(self.model.target_dstm)

        target_src_masked = self.model.target_src*target_srcm
        target_dst_masked = self.model.target_dst*target_dstm
        target_dst_anti_masked = self.model.target_dst*(1.0 - target_dstm)

        target_src_masked_opt = target_src_masked if masked_training else self.model.target_src
        target_dst_masked_opt = target_dst_masked if masked_training else self.model.target_dst

        pred_src_src_masked_opt = self.model.pred_src_src*target_srcm if masked_training else self.model.pred_src_src
        pred_dst_dst_masked_opt = self.model.pred_dst_dst*target_dstm if masked_training else self.model.pred_dst_dst

        psd_target_dst_masked = self.model.pred_src_dst*target_dstm
        psd_target_dst_anti_masked = self.model.pred_src_dst*(1.0 - target_dstm)

        if self.is_training_mode:
            self.src_dst_opt      = RMSprop(lr=5e-5, clipnorm=1.0 if self.options['clipgrad'] else 0.0, tf_cpu_mode=self.options['optimizer_mode']-1)
            self.src_dst_mask_opt = RMSprop(lr=5e-5, clipnorm=1.0 if self.options['clipgrad'] else 0.0, tf_cpu_mode=self.options['optimizer_mode']-1)
            self.D_opt            = RMSprop(lr=5e-5, clipnorm=1.0 if self.options['clipgrad'] else 0.0, tf_cpu_mode=self.options['optimizer_mode']-1)
            
            if not self.options['pixel_loss']:
                src_loss = K.mean ( 10*dssim(kernel_size=int(resolution/11.6),max_value=1.0)( target_src_masked_opt, pred_src_src_masked_opt) )
            else:
                src_loss = K.mean ( 50*K.square( target_src_masked_opt - pred_src_src_masked_opt ) )

            face_style_power = self.options['face_style_power'] / 100.0
            if face_style_power != 0:
                src_loss += style_loss(gaussian_blur_radius=resolution//16, loss_weight=face_style_power, wnd_size=0)( psd_target_dst_masked, target_dst_masked )

            bg_style_power = self.options['bg_style_power'] / 100.0
            if bg_style_power != 0:
                if not self.options['pixel_loss']:
                    src_loss += K.mean( (10*bg_style_power)*dssim(kernel_size=int(resolution/11.6),max_value=1.0)( psd_target_dst_anti_masked, target_dst_anti_masked ))
                else:
                    src_loss += K.mean( (50*bg_style_power)*K.square( psd_target_dst_anti_masked - target_dst_anti_masked ))

            if not self.options['pixel_loss']:
                dst_loss = K.mean( 10*dssim(kernel_size=int(resolution/11.6),max_value=1.0)(target_dst_masked_opt, pred_dst_dst_masked_opt) )
            else:
                dst_loss = K.mean( 50*K.square( target_dst_masked_opt - pred_dst_dst_masked_opt ) )

            opt_D_loss = []
            if self.true_face_training:                
                def DLoss(labels,logits):
                    return K.mean(K.binary_crossentropy(labels,logits))
                    
                src_code_d = self.dis( self.model.src_code )
                src_code_d_ones = K.ones_like(src_code_d)
                src_code_d_zeros = K.zeros_like(src_code_d)
                dst_code_d = self.dis( self.model.dst_code )
                dst_code_d_ones = K.ones_like(dst_code_d)
                opt_D_loss = [ DLoss(src_code_d_ones, src_code_d) ]
                
                loss_D = (DLoss(dst_code_d_ones , dst_code_d) + \
                          DLoss(src_code_d_zeros, src_code_d) ) * 0.5

                self.D_train = K.function ([self.model.warped_src, self.model.warped_dst],[loss_D], self.D_opt.get_updates(loss_D, self.dis.trainable_weights) )
                
            self.src_dst_train = K.function ([self.model.warped_src, self.model.warped_dst, self.model.target_src, self.model.target_srcm, self.model.target_dst, self.model.target_dstm],
                                             [src_loss,dst_loss], 
                                             self.src_dst_opt.get_updates( [src_loss+dst_loss]+opt_D_loss, self.model.src_dst_trainable_weights) 
                                             )

            if self.options['learn_mask']:
                src_mask_loss = K.mean(K.square(self.model.target_srcm-self.model.pred_src_srcm))
                dst_mask_loss = K.mean(K.square(self.model.target_dstm-self.model.pred_dst_dstm))
                self.src_dst_mask_train = K.function ([self.model.warped_src, self.model.warped_dst, self.model.target_srcm, self.model.target_dstm],[src_mask_loss, dst_mask_loss], self.src_dst_mask_opt.get_updates(src_mask_loss+dst_mask_loss, self.model.src_dst_mask_trainable_weights ) )

            if self.options['learn_mask']:
                self.AE_view = K.function ([self.model.warped_src, self.model.warped_dst], [self.model.pred_src_src, self.model.pred_dst_dst, self.model.pred_dst_dstm, self.model.pred_src_dst, self.model.pred_src_dstm])
            else:
                self.AE_view = K.function ([self.model.warped_src, self.model.warped_dst], [self.model.pred_src_src, self.model.pred_dst_dst, self.model.pred_src_dst ])

        else:
            if self.options['learn_mask']:
                self.AE_convert = K.function ([self.model.warped_dst],[ self.model.pred_src_dst, self.model.pred_dst_dstm, self.model.pred_src_dstm ])
            else:
                self.AE_convert = K.function ([self.model.warped_dst],[ self.model.pred_src_dst ])


        if self.is_training_mode:
            t = SampleProcessor.Types
            
            if self.options['face_type'] == 'h':
                face_type = t.FACE_TYPE_HALF
            elif self.options['face_type'] == 'mf':
                face_type = t.FACE_TYPE_MID_FULL
            elif self.options['face_type'] == 'f':
                face_type = t.FACE_TYPE_FULL
                
            t_mode_bgr = t.MODE_BGR if not self.pretrain else t.MODE_BGR_SHUFFLE

            training_data_src_path = self.training_data_src_path
            training_data_dst_path = self.training_data_dst_path
            sort_by_yaw = self.sort_by_yaw

            if self.pretrain and self.pretraining_data_path is not None:
                training_data_src_path = self.pretraining_data_path
                training_data_dst_path = self.pretraining_data_path
                sort_by_yaw = False

            self.set_training_data_generators ([
                    SampleGeneratorFace(training_data_src_path, sort_by_yaw_target_samples_path=training_data_dst_path if sort_by_yaw else None,
                                                                random_ct_samples_path=training_data_dst_path if apply_random_ct else None,
                                                                debug=self.is_debug(), batch_size=self.batch_size,
                        sample_process_options=SampleProcessor.Options(random_flip=self.random_flip, scale_range=np.array([-0.05, 0.05])+self.src_scale_mod / 100.0 ),
                        output_sample_types = [ {'types' : (t.IMG_WARPED_TRANSFORMED, face_type, t_mode_bgr), 'resolution':resolution, 'apply_ct': apply_random_ct},
                                                {'types' : (t.IMG_TRANSFORMED, face_type, t_mode_bgr), 'resolution': resolution, 'apply_ct': apply_random_ct },
                                                {'types' : (t.IMG_TRANSFORMED, face_type, t.MODE_M), 'resolution': resolution } ]
                         ),

                    SampleGeneratorFace(training_data_dst_path, debug=self.is_debug(), batch_size=self.batch_size,
                        sample_process_options=SampleProcessor.Options(random_flip=self.random_flip, ),
                        output_sample_types = [ {'types' : (t.IMG_WARPED_TRANSFORMED, face_type, t_mode_bgr), 'resolution':resolution},
                                                {'types' : (t.IMG_TRANSFORMED, face_type, t_mode_bgr), 'resolution': resolution},
                                                {'types' : (t.IMG_TRANSFORMED, face_type, t.MODE_M), 'resolution': resolution} ])
                             ])

    #override
    def get_model_filename_list(self):
        return self.model.get_model_filename_list ( exclude_for_pretrain=(self.pretrain and self.iter != 0) ) +self.opt_dis_model

    #override
    def onSave(self):
        self.save_weights_safe( self.get_model_filename_list()+self.opt_dis_model )

    #override
    def onTrainOneIter(self, generators_samples, generators_list):
        warped_src, target_src, target_srcm = generators_samples[0]
        warped_dst, target_dst, target_dstm = generators_samples[1]

        feed = [warped_src, warped_dst, target_src, target_srcm, target_dst, target_dstm]

        src_loss, dst_loss, = self.src_dst_train (feed)
        
        if self.true_face_training:
            self.D_train([warped_src, warped_dst])                

        if self.options['learn_mask']:
            feed = [ warped_src, warped_dst, target_srcm, target_dstm ]
            src_mask_loss, dst_mask_loss, = self.src_dst_mask_train (feed)

        return ( ('src_loss', src_loss), ('dst_loss', dst_loss), )

    #override
    def onGetPreview(self, sample):
        test_S   = sample[0][1][0:4] #first 4 samples
        test_S_m = sample[0][2][0:4] #first 4 samples
        test_D   = sample[1][1][0:4]
        test_D_m = sample[1][2][0:4]

        if self.options['learn_mask']:
            S, D, SS, DD, DDM, SD, SDM = [ np.clip(x, 0.0, 1.0) for x in ([test_S,test_D] + self.AE_view ([test_S, test_D]) ) ]
            DDM, SDM, = [ np.repeat (x, (3,), -1) for x in [DDM, SDM] ]
        else:
            S, D, SS, DD, SD, = [ np.clip(x, 0.0, 1.0) for x in ([test_S,test_D] + self.AE_view ([test_S, test_D]) ) ]

        result = []
        st = []
        for i in range(len(test_S)):
            ar = S[i], SS[i], D[i], DD[i], SD[i]

            st.append ( np.concatenate ( ar, axis=1) )

        result += [ ('SAE', np.concatenate (st, axis=0 )), ]

        if self.options['learn_mask']:
            st_m = []
            for i in range(len(test_S)):
                ar = S[i]*test_S_m[i], SS[i], D[i]*test_D_m[i], DD[i]*DDM[i], SD[i]*(DDM[i]*SDM[i])
                st_m.append ( np.concatenate ( ar, axis=1) )

            result += [ ('SAE masked', np.concatenate (st_m, axis=0 )), ]

        return result

    def predictor_func (self, face=None, dummy_predict=False):
        if dummy_predict:
            self.AE_convert ([ np.zeros ( (1, self.options['resolution'], self.options['resolution'], 3), dtype=np.float32 ) ])
        else:
            if self.options['learn_mask']:
                bgr, mask_dst_dstm, mask_src_dstm = self.AE_convert ([face[np.newaxis,...]])
                mask = mask_dst_dstm[0] * mask_src_dstm[0]
                return bgr[0], mask[...,0]
            else:
                bgr, = self.AE_convert ([face[np.newaxis,...]])
                return bgr[0]

    #override
    def get_ConverterConfig(self):
        if self.options['face_type'] == 'h':
            face_type = FaceType.HALF
        elif self.options['face_type'] == 'mf':
            face_type = FaceType.MID_FULL
        elif self.options['face_type'] == 'f':
            face_type = FaceType.FULL

        import converters
        return self.predictor_func, (self.options['resolution'], self.options['resolution'], 3), converters.ConverterConfigMasked(face_type=face_type,
                                     default_mode = 1 if self.options['apply_random_ct'] or self.options['face_style_power'] or self.options['bg_style_power'] else 4,
                                     clip_hborder_mask_per=0.0625 if (face_type == FaceType.FULL) else 0,
                                    )

Model = SAEv2Model
