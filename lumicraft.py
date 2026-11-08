bl_info = {
    "name": "LumiCraft",
    "author": "Utkarsh",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "Properties > Light Data",
    "description": "Advanced Area Light Engine: Soft Edges, Corner Rounding, Gobo Projection, Barn Doors, and live two-way Shader Editor sync.",
    "category": "Lighting",
    "license": "MIT",
}

import bpy
from bpy.props import BoolProperty, FloatProperty, EnumProperty, PointerProperty, FloatVectorProperty

ADDON_ID = "lumicraft"

class SmoothLightAddonPreferences(bpy.types.AddonPreferences):
    bl_idname = ADDON_ID

    enable_by_default: BoolProperty(
        name="Enable Smooth Light on New Area Lights by Default",
        description="If enabled, newly created Area Lights will have Smooth Light enabled automatically. Default is OFF.",
        default=False,
    )

    enable_experimental_features: BoolProperty(
        name="Enable Experimental Features (Shadow Tinting)",
        description="Show experimental features like Cinematic Shadow Tinting Helper in the Light Data panel. Default is OFF.",
        default=False,
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "enable_by_default")
        layout.prop(self, "enable_experimental_features")

def get_light_from_context(context):
    """Safely retrieves active light datablock from context without AttributeError"""
    if hasattr(context, 'light') and context.light:
        return context.light
    if context.active_object and context.active_object.type == 'LIGHT':
        return context.active_object.data
    return None

def get_or_create_shadow_tint_node_group():
    """Automates creation of modular 'Smooth_Cinematic_Shadow_Tint' Shader Node Group"""
    group_name = 'Smooth_Cinematic_Shadow_Tint'
    ng = bpy.data.node_groups.get(group_name)
    if ng:
        return ng
        
    ng = bpy.data.node_groups.new(name=group_name, type='ShaderNodeTree')
    ng.nodes.clear()
    ng.interface.clear()

    # Create Group Interface Sockets
    ng.interface.new_socket(name='Surface BSDF', in_out='INPUT', socket_type='NodeSocketShader')
    in_color = ng.interface.new_socket(name='Shadow Tint Color', in_out='INPUT', socket_type='NodeSocketColor')
    in_enable = ng.interface.new_socket(name='Enable Tint', in_out='INPUT', socket_type='NodeSocketFloat')

    ng.interface.new_socket(name='Shader', in_out='OUTPUT', socket_type='NodeSocketShader')

    in_color.default_value = (0.1, 0.45, 0.95, 1.0)
    in_enable.default_value = 1.0

    # Inside Inner Nodes Construction
    g_in = ng.nodes.new('NodeGroupInput')
    g_in.location = (-600, 0)

    g_out = ng.nodes.new('NodeGroupOutput')
    g_out.location = (600, 0)

    light_path = ng.nodes.new('ShaderNodeLightPath')
    light_path.location = (-400, 300)

    transparent = ng.nodes.new('ShaderNodeBsdfTransparent')
    transparent.location = (0, -100)

    shadow_fac_mult = ng.nodes.new('ShaderNodeMath')
    shadow_fac_mult.operation = 'MULTIPLY'
    shadow_fac_mult.location = (-200, 200)

    mix_shader = ng.nodes.new('ShaderNodeMixShader')
    mix_shader.location = (300, 0)

    # Wire internal nodes
    ng.links.new(g_in.outputs['Shadow Tint Color'], transparent.inputs['Color'])

    ng.links.new(light_path.outputs['Is Shadow Ray'], shadow_fac_mult.inputs[0])
    ng.links.new(g_in.outputs['Enable Tint'], shadow_fac_mult.inputs[1])

    ng.links.new(shadow_fac_mult.outputs['Value'], mix_shader.inputs['Fac'])
    ng.links.new(g_in.outputs['Surface BSDF'], mix_shader.inputs[1])
    ng.links.new(transparent.outputs['BSDF'], mix_shader.inputs[2])

    ng.links.new(mix_shader.outputs['Shader'], g_out.inputs['Shader'])
    return ng

def on_target_update(self, context):
    light_data = self
    target = light_data.sl_target_object
    
    for obj in bpy.data.objects:
        if obj.type == 'LIGHT' and obj.data == light_data:
            track_const = None
            for c in obj.constraints:
                if c.type == 'TRACK_TO' and c.name == 'Smooth_Target_Constraint':
                    track_const = c
                    break
            
            if target:
                if not track_const:
                    track_const = obj.constraints.new('TRACK_TO')
                    track_const.name = 'Smooth_Target_Constraint'
                track_const.target = target
                track_const.track_axis = 'TRACK_NEGATIVE_Z'
                track_const.up_axis = 'UP_Y'
            else:
                if track_const:
                    obj.constraints.remove(track_const)

def on_shadow_props_update(self, context):
    """Live update callback for shadow tint color and enable toggle"""
    light = self
    obj = light.sl_shadow_tint_object
    if obj and obj.type == 'MESH' and obj.active_material:
        mat = obj.active_material
        if mat.use_nodes and mat.node_tree:
            for n in mat.node_tree.nodes:
                if n.type == 'GROUP' and n.node_tree and n.node_tree.name == 'Smooth_Cinematic_Shadow_Tint':
                    if 'Shadow Tint Color' in n.inputs:
                        n.inputs['Shadow Tint Color'].default_value = tuple(light.sl_obj_shadow_color)
                    if 'Enable Tint' in n.inputs:
                        n.inputs['Enable Tint'].default_value = 1.0 if light.sl_obj_enable_tint else 0.0
    force_ui_redraw(context)

def update_barn_door_nodes(light):
    """Live update helper for Barn Door MapRange & Density nodes"""
    if not (light.use_nodes and light.node_tree):
        return
    tree = light.node_tree
    
    s_l = light.sl_barn_soft_left if light.sl_barn_use_independent_softness else light.sl_barn_softness
    s_r = light.sl_barn_soft_right if light.sl_barn_use_independent_softness else light.sl_barn_softness
    s_b = light.sl_barn_soft_bottom if light.sl_barn_use_independent_softness else light.sl_barn_softness
    s_t = light.sl_barn_soft_top if light.sl_barn_use_independent_softness else light.sl_barn_softness

    map_l = tree.nodes.get('SL_Barn_MapL')
    if map_l:
        map_l.inputs['From Min'].default_value = max(0.0, light.sl_barn_left - s_l * 0.5)
        map_l.inputs['From Max'].default_value = min(1.0, light.sl_barn_left + s_l * 0.5)

    map_r = tree.nodes.get('SL_Barn_MapR')
    if map_r:
        map_r.inputs['From Min'].default_value = max(0.0, light.sl_barn_right - s_r * 0.5)
        map_r.inputs['From Max'].default_value = min(1.0, light.sl_barn_right + s_r * 0.5)

    map_b = tree.nodes.get('SL_Barn_MapB')
    if map_b:
        map_b.inputs['From Min'].default_value = max(0.0, light.sl_barn_bottom - s_b * 0.5)
        map_b.inputs['From Max'].default_value = min(1.0, light.sl_barn_bottom + s_b * 0.5)

    map_t = tree.nodes.get('SL_Barn_MapT')
    if map_t:
        map_t.inputs['From Min'].default_value = max(0.0, light.sl_barn_top - s_t * 0.5)
        map_t.inputs['From Max'].default_value = min(1.0, light.sl_barn_top + s_t * 0.5)

    mult_den = tree.nodes.get('SL_Barn_MultDen')
    if mult_den:
        mult_den.inputs[1].default_value = light.sl_barn_density

def on_barn_door_update(self, context):
    update_barn_door_nodes(self)
    force_ui_redraw(context)

def on_corner_rounding_update(self, context):
    if self.use_nodes and self.node_tree:
        n_cr = self.node_tree.nodes.get('SL_Soft_CR_Val')
        if n_cr:
            n_cr.inputs[0].default_value = self.sl_corner_rounding
        n_inv_cr = self.node_tree.nodes.get('SL_Soft_InvCR_Val')
        if n_inv_cr:
            n_inv_cr.inputs[1].default_value = self.sl_corner_rounding
    force_ui_redraw(context)

def restore_default_light(light):
    if not light or light.type != 'AREA':
        return
    
    light.use_nodes = True
    tree = light.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()
    
    out_node = nodes.new('ShaderNodeOutputLight')
    out_node.location = (300, 0)
    
    emission = nodes.new('ShaderNodeEmission')
    emission.name = 'SL_Emission'
    emission.location = (0, 0)
    emission.inputs['Strength'].default_value = 1.0
    emission.inputs['Color'].default_value = tuple(light.color) + (1.0,) if len(light.color) == 3 else light.color
    
    links.new(emission.outputs['Emission'], out_node.inputs['Surface'])

def setup_smooth_light_nodes(light):
    """Constructs Smooth Light Shader Node Graph once when enabled or structural toggles change"""
    if not light or light.type != 'AREA':
        return
    
    light.use_nodes = True
    tree = light.node_tree
    nodes = tree.nodes
    links = tree.links
    nodes.clear()
    
    # --- 1. OUTPUT & EMISSION NODES ---
    out_node = nodes.new('ShaderNodeOutputLight')
    out_node.name = 'SL_Output'
    out_node.location = (1200, 0)
    
    emission = nodes.new('ShaderNodeEmission')
    emission.name = 'SL_Emission'
    emission.location = (900, 0)
    emission.inputs['Color'].default_value = tuple(light.color) + (1.0,) if len(light.color) == 3 else light.color
    
    links.new(emission.outputs['Emission'], out_node.inputs['Surface'])
    
    color_socket = emission.inputs['Color']

    # --- 2. GOBO TEXTURE PROJECTION ---
    if light.sl_use_gobo and light.sl_gobo_image:
        tc_gobo = nodes.new('ShaderNodeTexCoord')
        tc_gobo.name = 'SL_Gobo_TexCoord'
        tc_gobo.location = (-300, 500)
        
        mapping_gobo = nodes.new('ShaderNodeMapping')
        mapping_gobo.name = 'SL_Gobo_Mapping'
        mapping_gobo.vector_type = 'POINT'
        mapping_gobo.location = (-100, 500)
        mapping_gobo.inputs['Location'].default_value = (0.0, 0.0, 0.0)
        mapping_gobo.inputs['Scale'].default_value = (1.0, 1.0, 1.0)
        mapping_gobo.inputs['Rotation'].default_value = (0.0, 0.0, 0.0)
        links.new(tc_gobo.outputs['UV'], mapping_gobo.inputs['Vector'])
        
        img_node = nodes.new('ShaderNodeTexImage')
        img_node.name = 'SL_Gobo_Image'
        img_node.location = (100, 500)
        img_node.image = light.sl_gobo_image
        links.new(mapping_gobo.outputs['Vector'], img_node.inputs['Vector'])
        
        gobo_final_color = img_node.outputs['Color']
        
        if light.sl_gobo_affects_softness and light.sl_use_soft_edge:
            gobo_blur_mix = nodes.new('ShaderNodeMath')
            gobo_blur_mix.name = 'SL_Gobo_Blur'
            gobo_blur_mix.operation = 'MULTIPLY'
            gobo_blur_mix.location = (250, 550)
            gobo_blur_mix.inputs[1].default_value = 0.2
            links.new(img_node.outputs['Color'], gobo_blur_mix.inputs[0])
            gobo_final_color = gobo_blur_mix.outputs['Value']

        mix_gobo = nodes.new('ShaderNodeMath')
        mix_gobo.name = 'SL_Gobo_Mix'
        mix_gobo.operation = 'MULTIPLY'
        mix_gobo.location = (400, 400)
        mix_gobo.inputs[1].default_value = 1.0
        links.new(gobo_final_color, mix_gobo.inputs[0])
        links.new(mix_gobo.outputs['Value'], color_socket)

    # --- 3. UV PARAMETRIC & GEOMETRY NODES ---
    tc = nodes.new('ShaderNodeTexCoord')
    tc.name = 'SL_TexCoord'
    tc.location = (-1100, 0)
    
    sub_center = nodes.new('ShaderNodeVectorMath')
    sub_center.name = 'SL_SubCenter'
    sub_center.operation = 'SUBTRACT'
    sub_center.inputs[1].default_value = (0.5, 0.5, 0.0)
    sub_center.location = (-900, 0)
    links.new(tc.outputs['UV'], sub_center.inputs[0])
    
    current_mask_output = None
    
    # --- 4. SOFT EDGE MASK (SEPARABLE 2D RECTANGLE - MIN 0.01 TO MAX 1.0) ---
    if light.sl_use_soft_edge:
        abs_v = nodes.new('ShaderNodeVectorMath')
        abs_v.name = 'SL_AbsVector'
        abs_v.operation = 'ABSOLUTE'
        abs_v.location = (-750, 200)
        links.new(sub_center.outputs['Vector'], abs_v.inputs[0])
        
        sep = nodes.new('ShaderNodeSeparateXYZ')
        sep.name = 'SL_SepXYZ'
        sep.location = (-600, 200)
        links.new(abs_v.outputs['Vector'], sep.inputs['Vector'])
        
        v_soft = max(0.01, min(1.0, float(light.sl_softness)))
        from_min = 0.5 * (1.0 - v_soft)
        
        # 1D Map X
        map_x = nodes.new('ShaderNodeMapRange')
        map_x.name = 'SL_Soft_MapX'
        map_x.interpolation_type = 'SMOOTHSTEP'
        map_x.clamp = True
        map_x.location = (-400, 300)
        map_x.inputs['From Min'].default_value = from_min
        map_x.inputs['From Max'].default_value = 0.5
        map_x.inputs['To Min'].default_value = 1.0
        map_x.inputs['To Max'].default_value = 0.0
        links.new(sep.outputs['X'], map_x.inputs['Value'])
        
        # 1D Map Y
        map_y = nodes.new('ShaderNodeMapRange')
        map_y.name = 'SL_Soft_MapY'
        map_y.interpolation_type = 'SMOOTHSTEP'
        map_y.clamp = True
        map_y.location = (-400, 100)
        map_y.inputs['From Min'].default_value = from_min
        map_y.inputs['From Max'].default_value = 0.5
        map_y.inputs['To Min'].default_value = 1.0
        map_y.inputs['To Max'].default_value = 0.0
        links.new(sep.outputs['Y'], map_y.inputs['Value'])
        
        mult_rect = nodes.new('ShaderNodeMath')
        mult_rect.name = 'SL_MultRect'
        mult_rect.operation = 'MULTIPLY'
        mult_rect.location = (-200, 200)
        links.new(map_x.outputs['Result'], mult_rect.inputs[0])
        links.new(map_y.outputs['Result'], mult_rect.inputs[1])
        
        if light.sl_soft_shape == 'DISK' or light.sl_soft_shape == 'ROUNDED_RECT':
            dist_disk = nodes.new('ShaderNodeVectorMath')
            dist_disk.name = 'SL_DistDisk'
            dist_disk.operation = 'LENGTH'
            dist_disk.location = (-400, -100)
            links.new(sub_center.outputs['Vector'], dist_disk.inputs[0])
            
            map_disk = nodes.new('ShaderNodeMapRange')
            map_disk.name = 'SL_Soft_MapDisk'
            map_disk.interpolation_type = 'SMOOTHSTEP'
            map_disk.clamp = True
            map_disk.location = (-200, -100)
            map_disk.inputs['From Min'].default_value = from_min
            map_disk.inputs['From Max'].default_value = 0.5
            map_disk.inputs['To Min'].default_value = 1.0
            map_disk.inputs['To Max'].default_value = 0.0
            links.new(dist_disk.outputs['Value'], map_disk.inputs['Value'])

        if light.sl_soft_shape == 'DISK':
            current_mask_output = map_disk.outputs['Result']
        elif light.sl_soft_shape == 'ROUNDED_RECT':
            cr_val = max(0.0, min(1.0, float(light.sl_corner_rounding)))
            
            inv_cr = nodes.new('ShaderNodeMath')
            inv_cr.name = 'SL_Soft_InvCR_Val'
            inv_cr.operation = 'SUBTRACT'
            inv_cr.location = (-50, 300)
            inv_cr.inputs[0].default_value = 1.0
            inv_cr.inputs[1].default_value = cr_val
            
            cr_node = nodes.new('ShaderNodeMath')
            cr_node.name = 'SL_Soft_CR_Val'
            cr_node.operation = 'ADD'
            cr_node.location = (-50, -200)
            cr_node.inputs[0].default_value = cr_val
            cr_node.inputs[1].default_value = 0.0
            
            m_r = nodes.new('ShaderNodeMath')
            m_r.operation = 'MULTIPLY'
            m_r.location = (100, 200)
            links.new(mult_rect.outputs['Value'], m_r.inputs[0])
            links.new(inv_cr.outputs['Value'], m_r.inputs[1])
            
            m_d = nodes.new('ShaderNodeMath')
            m_d.operation = 'MULTIPLY'
            m_d.location = (100, 0)
            links.new(map_disk.outputs['Result'], m_d.inputs[0])
            links.new(cr_node.outputs['Value'], m_d.inputs[1])
            
            add_rr = nodes.new('ShaderNodeMath')
            add_rr.operation = 'ADD'
            add_rr.location = (250, 100)
            links.new(m_r.outputs['Value'], add_rr.inputs[0])
            links.new(m_d.outputs['Value'], add_rr.inputs[1])
            
            current_mask_output = add_rr.outputs['Value']
        else: # RECTANGLE
            current_mask_output = mult_rect.outputs['Value']

    # --- 5. BARN DOORS (4-WAY LINEAR FLAP CUTS) ---
    if light.sl_use_barn_doors:
        sep_uv = nodes.new('ShaderNodeSeparateXYZ')
        sep_uv.name = 'SL_Barn_SepUV'
        sep_uv.location = (-900, -300)
        links.new(tc.outputs['UV'], sep_uv.inputs['Vector'])
        
        s_l = light.sl_barn_soft_left if light.sl_barn_use_independent_softness else light.sl_barn_softness
        s_r = light.sl_barn_soft_right if light.sl_barn_use_independent_softness else light.sl_barn_softness
        s_b = light.sl_barn_soft_bottom if light.sl_barn_use_independent_softness else light.sl_barn_softness
        s_t = light.sl_barn_soft_top if light.sl_barn_use_independent_softness else light.sl_barn_softness

        map_l = nodes.new('ShaderNodeMapRange')
        map_l.name = 'SL_Barn_MapL'
        map_l.interpolation_type = 'SMOOTHSTEP'
        map_l.clamp = True
        map_l.location = (-700, -300)
        map_l.inputs['From Min'].default_value = max(0.0, light.sl_barn_left - s_l * 0.5)
        map_l.inputs['From Max'].default_value = min(1.0, light.sl_barn_left + s_l * 0.5)
        map_l.inputs['To Min'].default_value = 0.0
        map_l.inputs['To Max'].default_value = 1.0
        links.new(sep_uv.outputs['X'], map_l.inputs['Value'])
        
        map_r = nodes.new('ShaderNodeMapRange')
        map_r.name = 'SL_Barn_MapR'
        map_r.interpolation_type = 'SMOOTHSTEP'
        map_r.clamp = True
        map_r.location = (-700, -500)
        map_r.inputs['From Min'].default_value = max(0.0, light.sl_barn_right - s_r * 0.5)
        map_r.inputs['From Max'].default_value = min(1.0, light.sl_barn_right + s_r * 0.5)
        map_r.inputs['To Min'].default_value = 1.0
        map_r.inputs['To Max'].default_value = 0.0
        links.new(sep_uv.outputs['X'], map_r.inputs['Value'])
        
        map_b = nodes.new('ShaderNodeMapRange')
        map_b.name = 'SL_Barn_MapB'
        map_b.interpolation_type = 'SMOOTHSTEP'
        map_b.clamp = True
        map_b.location = (-500, -300)
        map_b.inputs['From Min'].default_value = max(0.0, light.sl_barn_bottom - s_b * 0.5)
        map_b.inputs['From Max'].default_value = min(1.0, light.sl_barn_bottom + s_b * 0.5)
        map_b.inputs['To Min'].default_value = 0.0
        map_b.inputs['To Max'].default_value = 1.0
        links.new(sep_uv.outputs['Y'], map_b.inputs['Value'])
        
        map_t = nodes.new('ShaderNodeMapRange')
        map_t.name = 'SL_Barn_MapT'
        map_t.interpolation_type = 'SMOOTHSTEP'
        map_t.clamp = True
        map_t.location = (-500, -500)
        map_t.inputs['From Min'].default_value = max(0.0, light.sl_barn_top - s_t * 0.5)
        map_t.inputs['From Max'].default_value = min(1.0, light.sl_barn_top + s_t * 0.5)
        map_t.inputs['To Min'].default_value = 1.0
        map_t.inputs['To Max'].default_value = 0.0
        links.new(sep_uv.outputs['Y'], map_t.inputs['Value'])
        
        m1 = nodes.new('ShaderNodeMath')
        m1.operation = 'MULTIPLY'
        m1.location = (-300, -350)
        links.new(map_l.outputs['Result'], m1.inputs[0])
        links.new(map_r.outputs['Result'], m1.inputs[1])
        
        m2 = nodes.new('ShaderNodeMath')
        m2.operation = 'MULTIPLY'
        m2.location = (-300, -500)
        links.new(map_b.outputs['Result'], m2.inputs[0])
        links.new(map_t.outputs['Result'], m2.inputs[1])
        
        barn_cut_raw = nodes.new('ShaderNodeMath')
        barn_cut_raw.operation = 'MULTIPLY'
        barn_cut_raw.location = (-100, -400)
        links.new(m1.outputs['Value'], barn_cut_raw.inputs[0])
        links.new(m2.outputs['Value'], barn_cut_raw.inputs[1])
        
        mult_den = nodes.new('ShaderNodeMath')
        mult_den.name = 'SL_Barn_MultDen'
        mult_den.operation = 'MULTIPLY'
        mult_den.location = (100, -400)
        mult_den.inputs[1].default_value = light.sl_barn_density
        links.new(barn_cut_raw.outputs['Value'], mult_den.inputs[0])
        
        barn_final = mult_den.outputs['Value']
        
        if light.sl_barn_invert:
            inv_node = nodes.new('ShaderNodeMath')
            inv_node.name = 'SL_Barn_Invert'
            inv_node.operation = 'SUBTRACT'
            inv_node.location = (250, -400)
            inv_node.inputs[0].default_value = 1.0
            links.new(mult_den.outputs['Value'], inv_node.inputs[1])
            barn_final = inv_node.outputs['Value']

        if current_mask_output:
            comb = nodes.new('ShaderNodeMath')
            comb.operation = 'MULTIPLY'
            comb.location = (550, -100)
            links.new(current_mask_output, comb.inputs[0])
            links.new(barn_final, comb.inputs[1])
            current_mask_output = comb.outputs['Value']
        else:
            current_mask_output = barn_final

    # --- 6. FINAL EMISSION POWER MULTIPLY (SL_Final_Mult) ---
    mult_pow = nodes.new('ShaderNodeMath')
    mult_pow.name = 'SL_Final_Mult'
    mult_pow.operation = 'MULTIPLY'
    mult_pow.location = (850, 0)
    mult_pow.inputs[0].default_value = float(light.get('sl_emission_strength', 1.0))
    if current_mask_output:
        links.new(current_mask_output, mult_pow.inputs[1])
    else:
        mult_pow.inputs[1].default_value = 1.0
    
    links.new(mult_pow.outputs['Value'], emission.inputs['Strength'])

# --- LIVE TWO-WAY GETTER / SETTER FUNCTIONS FOR 100% SHADER EDITOR SYNC ---
def get_emission_strength(self):
    if self.use_nodes and self.node_tree:
        node = self.node_tree.nodes.get('SL_Final_Mult')
        if node:
            return node.inputs[0].default_value
    return self.get('sl_emission_strength', 1.0)

def set_emission_strength(self, val):
    v = max(0.0, float(val))
    self['sl_emission_strength'] = v
    if self.use_nodes and self.node_tree:
        node = self.node_tree.nodes.get('SL_Final_Mult')
        if node:
            node.inputs[0].default_value = v

def get_softness(self):
    if self.use_nodes and self.node_tree:
        node = self.node_tree.nodes.get('SL_Soft_MapX') or self.node_tree.nodes.get('SL_Soft_MapDisk')
        if node:
            from_min = node.inputs['From Min'].default_value
            return max(0.01, min(1.0, 1.0 - 2.0 * from_min))
    return self.get('sl_softness', 0.5)

def set_softness(self, val):
    v = max(0.01, min(1.0, float(val)))
    self['sl_softness'] = v
    if self.use_nodes and self.node_tree:
        from_min = 0.5 * (1.0 - v)
        for name in ['SL_Soft_MapX', 'SL_Soft_MapY', 'SL_Soft_MapDisk']:
            node = self.node_tree.nodes.get(name)
            if node:
                node.inputs['From Min'].default_value = from_min
                
        # Gobo blur mix sync
        g_node = self.node_tree.nodes.get('SL_Gobo_Blur')
        if g_node:
            g_node.inputs[1].default_value = min(1.0, v * 0.4)

def get_gobo_loc_x(self):
    if self.use_nodes and self.node_tree:
        node = self.node_tree.nodes.get('SL_Gobo_Mapping')
        if node:
            return node.inputs['Location'].default_value[0]
    return self.get('sl_gobo_location_x', 0.0)

def set_gobo_loc_x(self, val):
    self['sl_gobo_location_x'] = val
    if self.use_nodes and self.node_tree:
        node = self.node_tree.nodes.get('SL_Gobo_Mapping')
        if node:
            node.inputs['Location'].default_value[0] = val

def get_gobo_loc_y(self):
    if self.use_nodes and self.node_tree:
        node = self.node_tree.nodes.get('SL_Gobo_Mapping')
        if node:
            return node.inputs['Location'].default_value[1]
    return self.get('sl_gobo_location_y', 0.0)

def set_gobo_loc_y(self, val):
    self['sl_gobo_location_y'] = val
    if self.use_nodes and self.node_tree:
        node = self.node_tree.nodes.get('SL_Gobo_Mapping')
        if node:
            node.inputs['Location'].default_value[1] = val

def get_gobo_scale_x(self):
    if self.use_nodes and self.node_tree:
        node = self.node_tree.nodes.get('SL_Gobo_Mapping')
        if node:
            return node.inputs['Scale'].default_value[0]
    return self.get('sl_gobo_scale_x', 1.0)

def set_gobo_scale_x(self, val):
    self['sl_gobo_scale_x'] = val
    if self.use_nodes and self.node_tree:
        node = self.node_tree.nodes.get('SL_Gobo_Mapping')
        if node:
            node.inputs['Scale'].default_value[0] = val

def get_gobo_scale_y(self):
    if self.use_nodes and self.node_tree:
        node = self.node_tree.nodes.get('SL_Gobo_Mapping')
        if node:
            return node.inputs['Scale'].default_value[1]
    return self.get('sl_gobo_scale_y', 1.0)

def set_gobo_scale_y(self, val):
    self['sl_gobo_scale_y'] = val
    if self.use_nodes and self.node_tree:
        node = self.node_tree.nodes.get('SL_Gobo_Mapping')
        if node:
            node.inputs['Scale'].default_value[1] = val

def get_gobo_rotation(self):
    if self.use_nodes and self.node_tree:
        node = self.node_tree.nodes.get('SL_Gobo_Mapping')
        if node:
            return node.inputs['Rotation'].default_value[2]
    return self.get('sl_gobo_rotation', 0.0)

def set_gobo_rotation(self, val):
    self['sl_gobo_rotation'] = val
    if self.use_nodes and self.node_tree:
        node = self.node_tree.nodes.get('SL_Gobo_Mapping')
        if node:
            node.inputs['Rotation'].default_value[2] = val

def on_toggles_rebuild(self, context):
    """Rebuilds graph structure cleanly when feature toggles change"""
    setup_smooth_light_nodes(self)

def force_ui_redraw(context):
    if context and hasattr(context, 'window_manager') and context.window_manager:
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()

# --- MODULAR SHADOW TINT NODE GROUP OPERATORS ---
class OBJECT_OT_add_object_shadow_tint(bpy.types.Operator):
    """Add/Append modular 'Smooth_Cinematic_Shadow_Tint' Node Group to Target Mesh Object"""
    bl_idname = "object.add_object_shadow_tint"
    bl_label = "Add Shadow Tint Node Group"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        light = get_light_from_context(context)
        obj = light.sl_shadow_tint_object if (light and light.sl_shadow_tint_object) else context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'WARNING'}, "Please select a Mesh Object using the Dropdown / Eyedropper!")
            return {'CANCELLED'}
            
        mat = obj.active_material
        if not mat:
            mat = bpy.data.materials.new(name=f"SL_Shadow_Tint_{obj.name}")
            if len(obj.data.materials) == 0:
                obj.data.materials.append(mat)
            else:
                obj.data.materials[0] = mat
        obj.active_material = mat
            
        mat.use_nodes = True
        tree = mat.node_tree
        nodes = tree.nodes
        
        ng = get_or_create_shadow_tint_node_group()
        
        group_node = None
        for n in nodes:
            if n.type == 'GROUP' and n.node_tree and n.node_tree.name == 'Smooth_Cinematic_Shadow_Tint':
                group_node = n
                break
                
        if not group_node:
            group_node = nodes.new('ShaderNodeGroup')
            group_node.node_tree = ng
            group_node.name = 'Smooth_Cinematic_Shadow_Tint'
            group_node.label = 'Smooth Shadow Tint'
            group_node.location = (300, 200)
            
        if light:
            if 'Shadow Tint Color' in group_node.inputs:
                group_node.inputs['Shadow Tint Color'].default_value = tuple(light.sl_obj_shadow_color)
            if 'Enable Tint' in group_node.inputs:
                group_node.inputs['Enable Tint'].default_value = 1.0 if light.sl_obj_enable_tint else 0.0
                    
        force_ui_redraw(context)
        self.report({'INFO'}, f"Added 'Smooth_Cinematic_Shadow_Tint' Node Group to '{obj.name}'!")
        return {'FINISHED'}

class OBJECT_OT_remove_object_shadow_tint(bpy.types.Operator):
    """Remove Shadow Tint Node Group from Target Mesh Object"""
    bl_idname = "object.remove_object_shadow_tint"
    bl_label = "Remove Shadow Tint Node Group"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        light = get_light_from_context(context)
        obj = light.sl_shadow_tint_object if (light and light.sl_shadow_tint_object) else context.active_object
        
        if not obj or obj.type != 'MESH' or not obj.active_material:
            return {'CANCELLED'}
            
        mat = obj.active_material
        tree = mat.node_tree
        nodes = tree.nodes
        
        for n in list(nodes):
            if n.type == 'GROUP' and n.node_tree and n.node_tree.name == 'Smooth_Cinematic_Shadow_Tint':
                nodes.remove(n)
                
        force_ui_redraw(context)
        self.report({'INFO'}, f"Removed Shadow Tint Node Group from '{obj.name}'!")
        return {'FINISHED'}

class OBJECT_OT_enable_smooth_light(bpy.types.Operator):
    """Enable Smooth Light setup on active Area Light"""
    bl_idname = "object.enable_smooth_light"
    bl_label = "Enable Smooth Light"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if obj and obj.type == 'LIGHT' and obj.data.type == 'AREA':
            light = obj.data
            light.sl_use_smooth_light = True
            setup_smooth_light_nodes(light)
            force_ui_redraw(context)
            self.report({'INFO'}, "Enabled Smooth Light setup.")
        return {'FINISHED'}

class OBJECT_OT_remove_smooth_light(bpy.types.Operator):
    """Completely remove Smooth Light nodes and restore default light"""
    bl_idname = "object.remove_smooth_light"
    bl_label = "Remove Smooth Light"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if obj and obj.type == 'LIGHT' and obj.data.type == 'AREA':
            light = obj.data
            light.sl_use_smooth_light = False
            restore_default_light(light)
            force_ui_redraw(context)
            self.report({'INFO'}, "Removed Smooth Light setup.")
        return {'FINISHED'}

class DATA_PT_smooth_pro_light(bpy.types.Panel):
    """LumiCraft Controls in Light Data Properties"""
    bl_label = "Smooth Light Engine"
    bl_idname = "DATA_PT_smooth_pro_light"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        return context.light and context.light.type == 'AREA'

    def draw(self, context):
        layout = self.layout
        light = context.light
        
        # --- LIGHT TARGET LOCK ---
        box_target = layout.box()
        box_target.prop(light, "sl_target_object", text="Target Object", icon='OBJECT_DATA')
        
        if not light.sl_use_smooth_light:
            layout.operator("object.enable_smooth_light", text="Enable Smooth Light", icon='NODE')
            return
            
        box_header = layout.box()
        row = box_header.row(align=True)
        row.label(text="Smooth Light Active", icon='CHECKMARK')
        row.operator("object.remove_smooth_light", text="Remove Light Setup", icon='TRASH')
        
        # --- EXPERIMENTAL: OBJECT SHADOW TINTING HELPER ---
        prefs = context.preferences.addons.get(ADDON_ID)
        show_experimental = prefs.preferences.enable_experimental_features if (prefs and hasattr(prefs, 'preferences')) else False
        
        if show_experimental:
            box_st = layout.box()
            box_st.label(text="Object Shadow Tint Helper (Experimental)", icon='COLOR')
            col_st = box_st.column(align=True)
            col_st.prop(light, "sl_shadow_tint_object", text="Shadow Caster", icon='OBJECT_DATA')
            col_st.prop(light, "sl_obj_enable_tint", text="Enable Shadow Tint", toggle=True)
            col_st.prop(light, "sl_obj_shadow_color", text="Shadow Color")
                
            row_st = col_st.row(align=True)
            row_st.operator("object.add_object_shadow_tint", text="Add Shadow Tint Node Group 📦", icon='NODETREE')
            row_st.operator("object.remove_object_shadow_tint", text="Remove Tint 🗑️", icon='TRASH')

        # --- EMISSION CONTROLS ---
        box_em = layout.box()
        box_em.label(text="Emission Power", icon='LIGHT_SUN')
        col = box_em.column(align=True)
        col.prop(light, "sl_emission_strength", text="Strength")

        # --- EDGE SOFTNESS WITH CORNER ROUNDING ---
        box = layout.box()
        box.prop(light, "sl_use_soft_edge", text="Enable Soft Edges", toggle=True)
        if light.sl_use_soft_edge:
            col = box.column(align=True)
            col.prop(light, "sl_softness", text="Softness Amount")
            col.prop(light, "sl_soft_shape", text="Edge Shape")
            if light.sl_soft_shape == 'ROUNDED_RECT':
                col.prop(light, "sl_corner_rounding", text="Corner Rounding", slider=True)
            
        # --- GOBO TEXTURE PROJECTION ---
        box = layout.box()
        box.prop(light, "sl_use_gobo", text="Enable Gobo / Softbox Texture", toggle=True)
        if light.sl_use_gobo:
            col = box.column(align=True)
            col.template_ID(light, "sl_gobo_image", open="image.open")
            
            row_loc = col.row(align=True)
            row_loc.prop(light, "sl_gobo_location_x", text="Location X")
            row_loc.prop(light, "sl_gobo_location_y", text="Location Y")
            
            row_scale = col.row(align=True)
            row_scale.prop(light, "sl_gobo_scale_x", text="Scale X")
            row_scale.prop(light, "sl_gobo_scale_y", text="Scale Y")
            
            col.prop(light, "sl_gobo_rotation", text="Rotation")
            col.prop(light, "sl_gobo_affects_softness", text="Affects Gobos (Link Light Softness)")

        # --- BARN DOORS ---
        box = layout.box()
        box.prop(light, "sl_use_barn_doors", text="Enable Barn Doors", toggle=True)
        if light.sl_use_barn_doors:
            col = box.column(align=True)
            col.prop(light, "sl_barn_density", slider=True, text="Flap Density / Opacity")
            col.prop(light, "sl_barn_invert", text="Invert Barn Doors (Window Aperture Frame)")
            col.prop(light, "sl_barn_use_independent_softness", text="Independent Per-Side Flap Softness")
            
            if light.sl_barn_use_independent_softness:
                box_ind = col.box()
                box_ind.label(text="Per-Side Softness", icon='MOD_EDGESPLIT')
                col_i = box_ind.column(align=True)
                col_i.prop(light, "sl_barn_soft_left", slider=True, text="Left Softness")
                col_i.prop(light, "sl_barn_soft_right", slider=True, text="Right Softness")
                col_i.prop(light, "sl_barn_soft_top", slider=True, text="Top Softness")
                col_i.prop(light, "sl_barn_soft_bottom", slider=True, text="Bottom Softness")
            else:
                col.prop(light, "sl_barn_softness", slider=True, text="Flap Softness")
                
            col.separator()
            col.label(text="Flap Positions:")
            col.prop(light, "sl_barn_left", slider=True, text="Left Flap")
            col.prop(light, "sl_barn_right", slider=True, text="Right Flap")
            col.prop(light, "sl_barn_top", slider=True, text="Top Flap")
            col.prop(light, "sl_barn_bottom", slider=True, text="Bottom Flap")

def register():
    bpy.types.Light.sl_shadow_tint_object = PointerProperty(
        type=bpy.types.Object,
        name="Shadow Caster",
        description="Select mesh object to apply custom shadow tinting"
    )

    bpy.types.Light.sl_obj_shadow_color = FloatVectorProperty(
        name="Object Shadow Color",
        subtype='COLOR',
        size=4,
        min=0.0, max=1.0,
        default=(0.1, 0.45, 0.95, 1.0),
        update=on_shadow_props_update
    )
    
    bpy.types.Light.sl_obj_enable_tint = BoolProperty(
        name="Enable Shadow Tint",
        description="Toggle shadow tinting on/off without removing nodes",
        default=True,
        update=on_shadow_props_update
    )

    bpy.types.Light.sl_target_object = PointerProperty(
        type=bpy.types.Object,
        name="Target Object",
        description="Object or mesh that this light will automatically track and point toward",
        update=on_target_update
    )
    
    bpy.types.Light.sl_emission_strength = FloatProperty(
        name="Emission Strength",
        description="Light emission strength (100% live sync with Shader Editor)",
        get=get_emission_strength,
        set=set_emission_strength,
        min=0.0,
        soft_max=100.0
    )
    
    bpy.types.Light.sl_use_smooth_light = BoolProperty(name="Use Smooth Light", default=False, update=on_toggles_rebuild)
    bpy.types.Light.sl_use_soft_edge = BoolProperty(name="Use Soft Edges", default=True, update=on_toggles_rebuild)
    
    bpy.types.Light.sl_softness = FloatProperty(
        name="Softness Amount",
        description="Edge softness amount (100% live sync with Shader Editor)",
        get=get_softness,
        set=set_softness,
        min=0.01,
        max=1.0
    )
    
    bpy.types.Light.sl_soft_shape = EnumProperty(
        name="Soft Shape",
        items=[
            ('RECTANGLE', "Rectangle", "Square / Rectangular light boundary"),
            ('ROUNDED_RECT', "Rounded Rect", "Rectangular light with smooth rounded corners"),
            ('DISK', "Disk", "Radial Disk / Circular light boundary")
        ],
        default='RECTANGLE',
        update=on_toggles_rebuild
    )

    bpy.types.Light.sl_corner_rounding = FloatProperty(
        name="Corner Rounding",
        description="Controls smooth corner curvature for rectangular soft edges",
        default=0.5,
        min=0.0,
        max=1.0,
        update=on_corner_rounding_update
    )
    
    bpy.types.Light.sl_use_gobo = BoolProperty(name="Use Gobo Texture", default=False, update=on_toggles_rebuild)
    bpy.types.Light.sl_gobo_image = PointerProperty(type=bpy.types.Image, name="Gobo Image", update=on_toggles_rebuild)
    
    bpy.types.Light.sl_gobo_location_x = FloatProperty(name="Gobo Location X", get=get_gobo_loc_x, set=set_gobo_loc_x, min=-10.0, max=10.0)
    bpy.types.Light.sl_gobo_location_y = FloatProperty(name="Gobo Location Y", get=get_gobo_loc_y, set=set_gobo_loc_y, min=-10.0, max=10.0)
    bpy.types.Light.sl_gobo_scale_x = FloatProperty(name="Gobo Scale X", get=get_gobo_scale_x, set=set_gobo_scale_x, min=0.01, max=10.0)
    bpy.types.Light.sl_gobo_scale_y = FloatProperty(name="Gobo Scale Y", get=get_gobo_scale_y, set=set_gobo_scale_y, min=0.01, max=10.0)
    bpy.types.Light.sl_gobo_rotation = FloatProperty(name="Gobo Rotation", get=get_gobo_rotation, set=set_gobo_rotation, subtype='ANGLE')
    bpy.types.Light.sl_gobo_affects_softness = BoolProperty(
        name="Affects Gobos",
        description="Matches light softness to gobo projection blur",
        default=True,
        update=on_toggles_rebuild
    )
    
    # Barn Door Controls
    bpy.types.Light.sl_use_barn_doors = BoolProperty(name="Use Barn Doors", default=False, update=on_toggles_rebuild)
    bpy.types.Light.sl_barn_density = FloatProperty(name="Flap Density", default=1.0, min=0.0, max=1.0, update=on_barn_door_update)
    bpy.types.Light.sl_barn_invert = BoolProperty(name="Invert Barn Doors", default=False, update=on_toggles_rebuild)
    bpy.types.Light.sl_barn_use_independent_softness = BoolProperty(name="Independent Per-Side Softness", default=False, update=on_toggles_rebuild)
    bpy.types.Light.sl_barn_softness = FloatProperty(name="Flap Softness", default=0.1, min=0.001, max=0.49, update=on_barn_door_update)
    bpy.types.Light.sl_barn_soft_left = FloatProperty(name="Left Softness", default=0.1, min=0.001, max=0.49, update=on_barn_door_update)
    bpy.types.Light.sl_barn_soft_right = FloatProperty(name="Right Softness", default=0.1, min=0.001, max=0.49, update=on_barn_door_update)
    bpy.types.Light.sl_barn_soft_top = FloatProperty(name="Top Softness", default=0.1, min=0.001, max=0.49, update=on_barn_door_update)
    bpy.types.Light.sl_barn_soft_bottom = FloatProperty(name="Bottom Softness", default=0.1, min=0.001, max=0.49, update=on_barn_door_update)
    
    bpy.types.Light.sl_barn_left = FloatProperty(name="Barn Left", default=0.0, min=0.0, max=0.49, update=on_barn_door_update)
    bpy.types.Light.sl_barn_right = FloatProperty(name="Barn Right", default=1.0, min=0.51, max=1.0, update=on_barn_door_update)
    bpy.types.Light.sl_barn_top = FloatProperty(name="Barn Top", default=1.0, min=0.51, max=1.0, update=on_barn_door_update)
    bpy.types.Light.sl_barn_bottom = FloatProperty(name="Barn Bottom", default=0.0, min=0.0, max=0.49, update=on_barn_door_update)

    bpy.utils.register_class(SmoothLightAddonPreferences)
    bpy.utils.register_class(OBJECT_OT_enable_smooth_light)
    bpy.utils.register_class(OBJECT_OT_remove_smooth_light)
    bpy.utils.register_class(OBJECT_OT_add_object_shadow_tint)
    bpy.utils.register_class(OBJECT_OT_remove_object_shadow_tint)
    bpy.utils.register_class(DATA_PT_smooth_pro_light)

def unregister():
    bpy.utils.unregister_class(SmoothLightAddonPreferences)
    bpy.utils.unregister_class(OBJECT_OT_enable_smooth_light)
    bpy.utils.unregister_class(OBJECT_OT_remove_smooth_light)
    bpy.utils.unregister_class(OBJECT_OT_add_object_shadow_tint)
    bpy.utils.unregister_class(OBJECT_OT_remove_object_shadow_tint)
    bpy.utils.unregister_class(DATA_PT_smooth_pro_light)

    del bpy.types.Light.sl_shadow_tint_object
    del bpy.types.Light.sl_obj_shadow_color
    del bpy.types.Light.sl_obj_enable_tint
    del bpy.types.Light.sl_target_object
    del bpy.types.Light.sl_emission_strength
    del bpy.types.Light.sl_use_smooth_light
    del bpy.types.Light.sl_use_soft_edge
    del bpy.types.Light.sl_softness
    del bpy.types.Light.sl_soft_shape
    del bpy.types.Light.sl_corner_rounding
    del bpy.types.Light.sl_use_gobo
    del bpy.types.Light.sl_gobo_image
    del bpy.types.Light.sl_gobo_location_x
    del bpy.types.Light.sl_gobo_location_y
    del bpy.types.Light.sl_gobo_scale_x
    del bpy.types.Light.sl_gobo_scale_y
    del bpy.types.Light.sl_gobo_rotation
    del bpy.types.Light.sl_gobo_affects_softness
    del bpy.types.Light.sl_use_barn_doors
    del bpy.types.Light.sl_barn_density
    del bpy.types.Light.sl_barn_invert
    del bpy.types.Light.sl_barn_use_independent_softness
    del bpy.types.Light.sl_barn_softness
    del bpy.types.Light.sl_barn_soft_left
    del bpy.types.Light.sl_barn_soft_right
    del bpy.types.Light.sl_barn_soft_top
    del bpy.types.Light.sl_barn_soft_bottom
    del bpy.types.Light.sl_barn_left
    del bpy.types.Light.sl_barn_right
    del bpy.types.Light.sl_barn_top
    del bpy.types.Light.sl_barn_bottom

if __name__ == "__main__":
    register()
