import time
import json
import math
import logging
from PIL import Image, ImageDraw, ImageFilter
import paths
from frontend.webui.image_variations_ui import generate_image_variations



def generate_upscaled_image(config, input_path = None, strength = 0.3, scale_factor = 2.0, tile_overlap = 16, upscale_settings = None):
    if config == None or (input_path == None or input_path == "" and upscale_settings == None):
        logging.error("Wrong arguments in tiled upscale function call!")
        return

    # Use the upscale_settings dict if provided; otherwise, build the 
    # upscale_settings dict using the function arguments and default values
    if upscale_settings == None:
        upscale_settings = {
            "source_file": input_path, 
            "target_file": None,
            "target_format": "jpg",
            "strength": strength,
            "scale_factor": scale_factor,
            "tile_overlap": tile_overlap,
            "tile_size": 256,
            "tiles": []
        }

    # Open/create input and output images
    source_image = Image.open(upscale_settings["source_file"])
    upscale_settings["source_image"] = source_image

    if upscale_settings["target_file"]:
        result = Image.open(upscale_settings["target_file"])
    else:
        result = Image.new(
            mode="RGBA", 
            size=(
                source_image.size[0] * int(upscale_settings["scale_factor"]), 
                source_image.size[1] * int(upscale_settings["scale_factor"])
            ), 
            color=(0, 0, 0, 0)
        )
    upscale_settings["target_image"] = result

    # If the custom tile definition array 'tiles' is empty, proceed with the 
    # default tiled upscale task by defining all the possible image tiles; note 
    # that the actual tile size is 'tile_size' + 'tile_overlap' and the target 
    # image width and height are no longer constrained to multiples of 256 but 
    # are instead multiples of the actual tile size
    if len(upscale_settings["tiles"]) == 0:
        tile_size = upscale_settings["tile_size"]
        scale_factor = upscale_settings["scale_factor"]
        tile_overlap = upscale_settings["tile_overlap"]
        total_cols = math.ceil(source_image.size[0] / tile_size)  # Image width / tile size
        total_rows = math.ceil(source_image.size[1] / tile_size)  # Image height / tile size
        for y in range(0, total_rows):
            y_offset = tile_overlap if y > 0 else 0               # Tile mask offset
            for x in range(0, total_cols):
                x_offset = tile_overlap if x > 0 else 0           # Tile mask offset
                x1 = x * tile_size
                y1 = y * tile_size
                w = tile_size + (tile_overlap if x < total_cols - 1 else 0)
                h = tile_size + (tile_overlap if y < total_rows - 1 else 0)
                mask_box = (                                      # Default tile mask box definiton
                    x_offset, y_offset, 
                    int(w * scale_factor), int(h * scale_factor)
                )
                upscale_settings["tiles"].append(
                    {"x": x1, "y": y1, "w": w, "h": h, "mask_box": mask_box, 
                     "prompt": None, "scale_factor": scale_factor}
                )

    # Generate the output image tiles
    for i in range(0, len(upscale_settings["tiles"])):
        generate_upscaled_tile(config, i, upscale_settings)

    # Save completed upscaled image
    output_name = "FastSD-" + str(int(time.time())) + "." + upscale_settings["target_format"];
    output_path = paths.join_paths(
        paths.FastStableDiffusionPaths.get_results_path(),
        output_name
    )
    logging.info("Saving " + output_path + "...")
    if (upscale_settings["target_format"] == "jpg"):
        result_rgb = result.convert("RGB")
        result.close()
        result = result_rgb
    result.save(output_path)
    result.close()
    source_image.close()
    return



# Generates a single tile from the source image as defined in the 
# upscale_settings["tiles"] array with the corresponding index and pastes the 
# generated tile into the target image using the corresponding mask and scale 
# factor; note that scale factor for the target image and the individual tiles 
# can be different, this function will adjust scale factors as needed
def generate_upscaled_tile(config, index, upscale_settings):
    if config == None or upscale_settings == None:
        logging.error("Wrong arguments in tile creation function call!")
        return

    x = upscale_settings["tiles"][index]["x"]
    y = upscale_settings["tiles"][index]["y"]
    w = upscale_settings["tiles"][index]["w"]
    h = upscale_settings["tiles"][index]["h"]
    tile_prompt = upscale_settings["tiles"][index]["prompt"]
    scale_factor = upscale_settings["scale_factor"]
    tile_scale_factor = upscale_settings["tiles"][index]["scale_factor"]
    target_width = int(w * tile_scale_factor)
    target_height = int(h * tile_scale_factor)
    strength = upscale_settings["strength"]
    source_image = upscale_settings["source_image"]
    target_image = upscale_settings["target_image"]
    mask_image = generate_tile_mask(config, index, upscale_settings)

    config.lcm_diffusion_setting.number_of_images = 1
    config.lcm_diffusion_setting.prompt = tile_prompt
    config.lcm_diffusion_setting.image_width = target_width
    config.lcm_diffusion_setting.image_height = target_height
    config.lcm_diffusion_setting.init_image = source_image.crop((x, y, x + w, y + h))

    current_tile = None
    if (True):
        logging.info(f"Generating tile {index + 1}/{len(upscale_settings['tiles'])} using Image variations...")
        current_tile = generate_image_variations(
            config.lcm_diffusion_setting.init_image, strength
        )[0]
#    else:
#        # An attempt to use img2img with low denoising strength to 
#        # generate the tiles with the extra aid of a prompt
#        logging.info(f"Generating tile {index + 1}/{len(upscale_settings['tiles'])} using img2img...")
#        context = get_context(InterfaceType.CLI)
#        current_tile = context.generate_text_to_image(
#            settings=config,
#            device=DEVICE,
#        )[0]
    if (math.isclose(scale_factor, tile_scale_factor)):
        target_image.paste(
            current_tile, (int(x * scale_factor), int(y * scale_factor)), mask_image
        )
    else:
        target_image.paste(
            current_tile.resize((int(w * scale_factor), int(h * scale_factor))), 
            (int(x * scale_factor), int(y * scale_factor)), 
            mask_image.resize((int(w * scale_factor), int(h * scale_factor)))
        )
    mask_image.close()
    current_tile.close()
    config.lcm_diffusion_setting.init_image.close()



# Generate tile mask using the box definition in the upscale_settings["tiles"] 
# array with the corresponding index; note that tile masks for the default 
# tiled upscale task can be reused but that would complicate the code, so 
# new tile masks are instead created for each tile
def generate_tile_mask(config, index, upscale_settings):
    scale_factor = upscale_settings["scale_factor"]
    tile_overlap = upscale_settings["tile_overlap"]
    tile_scale_factor = upscale_settings["tiles"][index]["scale_factor"]
    w = int(upscale_settings["tiles"][index]["w"] * tile_scale_factor)
    h = int(upscale_settings["tiles"][index]["h"] * tile_scale_factor)
    mask_box = upscale_settings["tiles"][index]["mask_box"]
    if mask_box == None:
        # Build a default solid mask with soft/transparent edges
        mask_box = (
            tile_overlap, tile_overlap, 
            w - tile_overlap, h - tile_overlap
        )
    mask_image = Image.new(mode="RGBA", size=(w, h), color=(0, 0, 0, 0))
    mask_draw = ImageDraw.Draw(mask_image)
    mask_draw.rectangle(tuple(mask_box), fill=(0, 0, 0))
    mask_blur = mask_image.filter(ImageFilter.BoxBlur(tile_overlap - 1))
    mask_image.close()
    return mask_blur

