// qrcode is heavy and only the kiosk welcome renders a QR, so it's imported
// lazily — it stays out of every other route's chunk.
export async function renderQR(canvas: HTMLCanvasElement, value: string): Promise<void> {
  const QRCode = await import('qrcode');
  await QRCode.toCanvas(canvas, value, {
    errorCorrectionLevel: 'M',
    margin: 2,
    width: canvas.width,
    color: {
      dark: '#18181b',
      light: '#ffffff',
    },
  });
}
