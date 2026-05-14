"""CrowdCanvas — Streamlit app: turn an image into a Craig-Alan-style crowd portrait.

Run with:
    pip install -r requirements.txt
    streamlit run app.py
"""

import hashlib
import os
import io
from pathlib import Path
import numpy as np
import streamlit as st
from PIL import Image
import base64
from database import init_db, save_image, load_gallery, create_user, verify_user, delete_image
from crowdcanvas import (
    detect_face_bbox,
    extract_subject_mask,
    generate_crowd,
    hex_to_rgb,
    load_sprites,
)

HERE = Path(__file__).parent
SPRITES_DIR = HERE / "Artwork people"
HERO_IMAGE = HERE / "hero.png"
init_db()

st.set_page_config(page_title="CrowdCanvas", page_icon="🧑‍🎨", layout="wide")

# Home Page
if "started" not in st.session_state:
    st.session_state.started = False

if "auth_mode" not in st.session_state:
    st.session_state.auth_mode = None

if "username" not in st.session_state:
    st.session_state.username = None

def image_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


if not st.session_state.started:
    hero_b64 = image_to_base64(HERO_IMAGE)

    st.markdown(f"""
<div style="text-align:center; padding-top:0vh;">
    <h1 style="font-size:4.5rem; margin-bottom:0.5rem;">CrowdCanvas</h1>
    <img src="data:image/png;base64,{hero_b64}" style="max-height:48vh; max-width:90%; object-fit:contain; border-radius:10px;">
    <p style="font-size:1.2rem; color:#888; margin-top:1rem; margin-bottom:1.5rem;">Transform images into crowd-based mosaic artwork</p>
</div>
""", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])

    with col2:
        if st.button("Start Creating", use_container_width=True):
            st.session_state.started = True
            st.session_state.page = "auth"
            st.rerun()

        if st.button("Exit App", use_container_width=True):
            os._exit(0)

    st.stop()

# Auth Page
def return_home():
    st.session_state.started = False
    st.session_state.auth_mode = None
    st.session_state.username = None
    st.session_state.page = "creator"
    st.rerun()

if st.session_state.page == "auth":
    st.title("Welcome to CrowdCanvas")
    st.caption("Sign in, create an account, or continue as a guest.")

    tab1, tab2, tab3 = st.tabs(["Sign In", "Sign Up", "Guest"])

    with tab1:
        username = st.text_input("Username", key="signin_username")
        password = st.text_input("Password", type="password", key="signin_password")

        if st.button("Sign In", use_container_width=True):
            if verify_user(username, password):
                st.session_state.auth_mode = "registered"
                st.session_state.username = username
                st.session_state.page = "creator"
                st.rerun()
            else:
                st.error("Invalid username or password.")
        
        if st.button("Cancel", key="signin_cancel", use_container_width=True):
            return_home()

    with tab2:
        new_username = st.text_input("Create username", key="signup_username")
        new_password = st.text_input("Create password", type="password", key="signup_password")

        if st.button("Sign Up", use_container_width=True):
            if create_user(new_username, new_password):
                st.success("Account created. You are now signed in.")
                st.session_state.auth_mode = "registered"
                st.session_state.username = new_username
                st.session_state.page = "creator"
                st.rerun()
            else:
                st.error("That username already exists.")

        if st.button("Cancel", key="signup_cancel", use_container_width=True):
            return_home()

    with tab3:
        if st.button("Continue as Guest", use_container_width=True):
            st.session_state.auth_mode = "guest"
            st.session_state.username = None
            st.session_state.page = "creator"
            st.rerun()

        if st.button("Cancel", key="guest_cancel", use_container_width=True):
            return_home()

    st.stop()

#Creator Page
if "page" not in st.session_state:
    st.session_state.page = "creator"

#Gallery Page
if st.session_state.page == "gallery":
    st.title("Gallery")

    rows = load_gallery(st.session_state.username)

    if not rows:
        st.info("No saved images yet.")
    else:
        cols = st.columns(3)

        for i, (img_id, image_data, created_at) in enumerate(rows):
            with cols[i % 3]:
                img = Image.open(io.BytesIO(image_data))

                st.image(img, use_container_width=True)
                st.caption(f"Created: {created_at}")

                st.download_button(
                    "Download",
                    data=image_data,
                    file_name=f"crowdcanvas_{img_id}.png",
                    mime="image/png",
                    key=f"download_{img_id}"
                )

                if st.button("Delete", key=f"delete_{img_id}"):
                    delete_image(st.session_state.username, img_id)
                    st.rerun()

    if st.button("Back to Creator"):
        st.session_state.page = "creator"
        st.rerun()

    st.stop()

st.title("CrowdCanvas")

col1, col2 = st.columns([1, 1])

with col1:
    st.write(f"Signed in as: {st.session_state.username or 'Guest'}")

with col2:
    if st.button("Sign Out"):
        return_home()

st.caption(
    "Upload an image — the app rebuilds it as a crowd of tiny figures, in the "
    "spirit of Craig Alan's *Populus* portraits. Works best with high-contrast "
    "subjects (faces, silhouettes, logos)."
)

#Gallery Page Button
if st.session_state.auth_mode == "registered":
    if st.button("View Gallery"):
        st.session_state.page = "gallery"
        st.rerun()
else:
    st.info("Guest mode: gallery access is only available to registered users.")

## Continue with Creator Page
@st.cache_resource(show_spinner="Loading people sprites…")
def _load_sprites_cached(path: str):
    return load_sprites(path)


sprites = _load_sprites_cached(str(SPRITES_DIR))
if not sprites:
    st.error(f"No PNG sprites found in `{SPRITES_DIR}`.")
    st.stop()
st.sidebar.success(f"Loaded {len(sprites)} people sprites")

with st.sidebar:
    st.header("Settings")
    subject_only = st.toggle(
        "Focus on subject only", value=True,
        help="Auto-removes the background so figures only land on the person/subject. "
             "First run downloads a ~170MB model.",
    )
    subject_model = st.selectbox(
        "Subject detector",
        options=["u2net_human_seg", "u2net", "isnet-general-use"],
        index=0,
        help="Use the human-seg model for portraits. Switch to 'u2net' / 'isnet' for "
             "non-human subjects (objects, animals, paintings).",
        disabled=not subject_only,
    )
    output_size = st.slider("Output size (px, longest side)", 800, 4000, 2000, 200)
    density_count = st.slider("Crowd density (figures placed)", 200, 10000, 2800, 100)
    scatter_count = st.slider(
        "Background scatter (stragglers)", 0, 500, 0, 5,
        help="Stragglers placed anywhere on the canvas, ignoring the subject mask. "
             "Set to 0 to keep figures strictly on the subject.",
    )

    st.markdown("**Face emphasis**")
    face_boost = st.slider(
        "Face boost", 1.0, 4.0, 2.4, 0.1,
        help="Multiplier on density inside the detected face. 1.0 = body and face equal; "
             "2.4 = face gets ~2.4× the figures of shoulders/torso.",
    )
    detail_strength = st.slider(
        "Detail enhancement", 0.0, 1.5, 0.6, 0.1,
        help="Sharpens edges before density extraction so eyes, lips, glasses, and hair "
             "strands register as denser regions.",
    )

    st.markdown("**Crowd behavior**")
    selectivity = st.slider(
        "Selectivity", 1.0, 6.0, 3.0, 0.2,
        help="How tightly figures cluster on dark features. Higher = sharper portrait, more empty space.",
    )
    min_density = st.slider(
        "Density floor", 0.00, 0.50, 0.10, 0.02,
        help="Pixels lighter than this never receive figures — keeps the background clean.",
    )
    sprite_height_pct = st.slider(
        "Person size (% of canvas height)", 0.008, 0.040, 0.015, 0.001,
        help="Smaller figures resolve finer features (eyes, mouth) but need more figures total.",
    )
    scale_jitter = st.slider("Size variation", 0.00, 0.50, 0.18, 0.05)
    gamma = st.slider(
        "Contrast (gamma)", 0.5, 3.0, 2.0, 0.1,
        help="Higher = denser dark areas, sharper crowd shapes.",
    )
    blur = st.slider("Smoothing radius", 0.0, 6.0, 1.0, 0.5)
    bg_hex = st.color_picker("Background color", "#F5F0E6")
    paper_grain = st.slider("Paper grain", 0.00, 0.05, 0.015, 0.005)
    seed_input = st.number_input(
        "Random seed (0 = random)", min_value=0, max_value=999_999, value=0, step=1
    )

uploaded = st.file_uploader(
    "Input image", type=["png", "jpg", "jpeg", "webp", "bmp", "tiff"]
)

if uploaded is None:
    st.info("Upload an image to begin. Tip: portraits with strong shadows look best.")
    st.stop()

raw_bytes = uploaded.getvalue()
input_img = Image.open(io.BytesIO(raw_bytes))


@st.cache_data(show_spinner="Extracting subject (first run downloads a ~170MB model)…")
def _cached_subject_mask(image_bytes: bytes, model: str) -> np.ndarray:
    img = Image.open(io.BytesIO(image_bytes))
    return extract_subject_mask(img, model=model)


subject_mask: np.ndarray | None = None
if subject_only:
    try:
        subject_mask = _cached_subject_mask(raw_bytes, subject_model)
        if float(subject_mask.max()) < 0.05:
            st.warning("Subject extraction returned an empty mask — falling back to whole image.")
            subject_mask = None
    except Exception as exc:  # network/model load problem — degrade gracefully
        st.warning(f"Subject extraction unavailable ({exc}); falling back to whole image.")
        subject_mask = None


@st.cache_data(show_spinner=False)
def _cached_face_bbox(image_bytes: bytes):
    img = Image.open(io.BytesIO(image_bytes))
    return detect_face_bbox(img)


face_bbox = _cached_face_bbox(raw_bytes) if face_boost > 1.0 else None

col_in, col_out = st.columns(2)
with col_in:
    st.subheader("Input")
    if face_bbox is not None:
        st.caption(f"✓ Face detected at {face_bbox} — face boost will apply.")
    elif face_boost > 1.0:
        st.caption("⚠ No face detected — face boost will have no effect.")
    st.image(input_img, use_column_width=True)
    if subject_mask is not None:
        with st.expander("Subject mask preview"):
            st.image(
                (subject_mask * 255).astype("uint8"),
                caption="White = where figures will be placed. Black = ignored.",
                use_column_width=True,
            )

with col_out:
    st.subheader("Crowd canvas")
    if st.button("Generate", type="primary", use_container_width=True):
        progress = st.progress(0.0, text="Painting the crowd…")

        def _cb(p: float) -> None:
            progress.progress(min(max(p, 0.0), 1.0), text="Painting the crowd…")

        output = generate_crowd(
            input_img,
            sprites,
            output_size=output_size,
            density_count=density_count,
            scatter_count=scatter_count,
            sprite_height_pct=sprite_height_pct,
            scale_jitter=scale_jitter,
            gamma=gamma,
            blur=blur,
            selectivity=selectivity,
            min_density=min_density,
            detail_strength=detail_strength,
            face_boost=face_boost,
            face_bbox=face_bbox,
            subject_only=subject_only,
            subject_mask=subject_mask,
            background_color=hex_to_rgb(bg_hex),
            paper_grain=paper_grain,
            seed=None if seed_input == 0 else int(seed_input),
            progress_callback=_cb,
        )
        if st.session_state.auth_mode == "registered":
            save_image(st.session_state.username, output)

        progress.empty()

        st.image(output, use_column_width=True)

        if st.session_state.auth_mode == "registered":
            buf = io.BytesIO()
            output.save(buf, format="PNG", optimize=True)
            st.download_button(
                "Download PNG",
                data=buf.getvalue(),
                file_name="crowdcanvas.png",
                mime="image/png",
                use_container_width=True,
            )
        else:
            st.warning("Guest mode: downloading and saving images is disabled.")
    else:
            st.caption("Adjust the sidebar settings, then press **Generate**.")
