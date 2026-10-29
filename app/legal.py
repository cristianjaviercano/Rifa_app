"""Versión vigente de los términos y la política de privacidad (public/js/legal.js).
Cambiar TERMS_VERSION obliga a aceptar de nuevo en el siguiente ingreso."""
import os

TERMS_VERSION = "2026-10-29-borrador"


def required() -> bool:
    v = os.environ.get("SGRS_REQUIRE_TERMS")
    return v == "1" or (v is None and os.environ.get("SGRS_ENV") == "production")
