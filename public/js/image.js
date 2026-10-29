/** Reduce fotos grandes del celular a ≤1600 px (JPEG): la subida es rápida y cabe en el límite de 4 MB. */
export async function prepareImage(file, maxSide = 1600, threshold = 900 * 1024) {
  if (!file.type.startsWith("image/") || file.size < threshold) return file;
  try {
    const bmp = await createImageBitmap(file);
    const k = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
    const c = document.createElement("canvas");
    c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
    c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
    const blob = await new Promise((res) => c.toBlob(res, "image/jpeg", 0.85));
    return blob && blob.size < file.size ? blob : file;
  } catch { return file; }
}
