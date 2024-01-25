import base64
from io import BytesIO

import keras_tuner as kt
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

from data_preprocessing import normalize_pixels, resize
from models import get_unet
from schemas import ImageModel
from tuners import tune_model_mse

app = FastAPI()

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

models = dict()

# load unet
tuner = kt.Hyperband(
    tune_model_mse,
    objective="val_loss",
    max_epochs=5,
    factor=3,
    directory="./params",
    project_name="cv_params_mse",
)

params = tuner.get_best_hyperparameters()[0]
activation = params.values["activation"]
depth = params.values["depth"]
dropout = params.values["dropout"]
optimizer = params.values["optimizer"]

model = get_unet(depth, dropout, activation)
model.load_weights("./weights/model_mse.15.h5")
models["unet"] = model


@app.post("/api/v1/{model_type}")
async def process_mobile_sam_onnx(image: ImageModel, model_type: str):
    """
    Input:
    - 'model' - name of the model (custom_1, custom_2, unet, unet_gan)
    Output:
    - 'image' - base64 string containing JPEG content
    """
    image_bytes = image.image_bytes

    # Convert image bytes to image
    image = Image.open(BytesIO(base64.b64decode(image_bytes)))
    image = np.array(image)
    image = resize(image)
    image = normalize_pixels(image)

    model = None
    try:
        model = models[model_type]
    except KeyError:
        return HTTPException(404, "Specified model not found")

    result = model.predict(image[np.newaxis])[0]
    result = ((1 - result) * 255.0).astype(np.uint8)
    result = np.repeat(result, 3, axis=-1)
    result = Image.fromarray(result)

    buffered = BytesIO()
    result.save(buffered, format="JPEG")
    ret_image = base64.b64encode(buffered.getvalue()).decode("utf-8")

    ret_str = ImageModel(image_bytes=ret_image)
    response = {"image": ret_str}
    return response