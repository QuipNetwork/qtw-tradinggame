import * as QRCode from 'qrcode';

export async function renderQR(canvas: HTMLCanvasElement, value: string): Promise<void> {
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
