/** @odoo-module **/

import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

class QrCameraScannerAction extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.videoRef = useRef("video");
        this.canvasRef = useRef("canvas");
        this.state = useState({
            scanning: false,
            supported: typeof window !== "undefined" && "BarcodeDetector" in window,
            result: "",
            error: "",
            saving: false,
        });
        this.stream = null;
        this.detector = null;
        this.scanTimer = null;
        this.serverScanTimer = null;
        this.params = this.props.action.params || {};
        onMounted(async () => {
            await this.startCamera();
        });
        onWillUnmount(() => {
            this.stopCamera();
        });
    }

    async startCamera() {
        this.state.error = "";
        if (!navigator.mediaDevices?.getUserMedia) {
            this.state.error = "Este navegador no soporta acceso a cámara.";
            return;
        }
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: { facingMode: { ideal: "environment" } },
                audio: false,
            });
            const video = this.videoRef.el;
            video.srcObject = this.stream;
            await video.play();
            this.state.scanning = true;
            if (this.state.supported) {
                const supportedFormats = await window.BarcodeDetector.getSupportedFormats();
                if (!supportedFormats.includes("qr_code")) {
                    this.state.error = "El navegador no soporta detector local QR. Activando fallback servidor...";
                    this.startServerFallbackLoop();
                    return;
                }
                this.detector = new window.BarcodeDetector({ formats: ["qr_code"] });
                this.scanLoop();
            } else {
                this.state.error = "BarcodeDetector no disponible. Activando fallback servidor...";
                this.startServerFallbackLoop();
            }
        } catch (err) {
            this.state.error = `No fue posible abrir la cámara: ${err.message || err}`;
        }
    }

    stopCamera() {
        this.state.scanning = false;
        if (this.scanTimer) {
            clearTimeout(this.scanTimer);
            this.scanTimer = null;
        }
        if (this.serverScanTimer) {
            clearTimeout(this.serverScanTimer);
            this.serverScanTimer = null;
        }
        if (this.stream) {
            this.stream.getTracks().forEach((t) => t.stop());
            this.stream = null;
        }
    }

    async scanLoop() {
        while (this.state.scanning && this.detector && this.videoRef.el) {
            try {
                const video = this.videoRef.el;
                const canvas = this.canvasRef.el;
                if (!video.videoWidth || !video.videoHeight) {
                    await sleep(250);
                    continue;
                }
                canvas.width = video.videoWidth;
                canvas.height = video.videoHeight;
                const ctx = canvas.getContext("2d", { willReadFrequently: true });
                ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                const codes = await this.detector.detect(canvas);
                if (codes && codes.length) {
                    const value = (codes[0].rawValue || "").trim();
                    if (value) {
                        this.state.result = value;
                        this.stopCamera();
                        await this.useResult();
                        return;
                    }
                }
            } catch (_err) {
                // Ignore detector transient errors.
            }
            await sleep(180);
        }
    }

    _captureFrameDataUrl() {
        const video = this.videoRef.el;
        const canvas = this.canvasRef.el;
        if (!video || !canvas || !video.videoWidth || !video.videoHeight) {
            return null;
        }
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", 0.92);
    }

    async startServerFallbackLoop() {
        const model = this.params.model;
        const resId = this.params.resId;
        if (!model || !resId) {
            this.state.error = "No se puede usar fallback sin modelo y registro.";
            return;
        }
        while (this.state.scanning) {
            try {
                const imageData = this._captureFrameDataUrl();
                if (imageData) {
                    const decoded = await this.orm.call(model, "action_decode_qr_image_from_camera", [[resId], imageData]);
                    if (decoded && String(decoded).trim()) {
                        this.state.result = String(decoded).trim();
                        this.stopCamera();
                        await this.useResult();
                        return;
                    }
                }
            } catch (_err) {
                // Ignore transient decode errors.
            }
            await sleep(550);
        }
    }

    async useResult() {
        if (this.state.saving) {
            return;
        }
        const qrValue = (this.state.result || "").trim();
        if (!qrValue) {
            this.notification.add("Escanea un QR o pega una URL.", { type: "warning" });
            return;
        }
        const model = this.params.model;
        const resId = this.params.resId;
        if (!model || !resId) {
            this.notification.add("Faltan parámetros de modelo para guardar el QR.", { type: "danger" });
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call(model, "action_set_qr_url_from_camera", [[resId], qrValue], { auto_validate: true });
            this.notification.add("QR detectado, guardado y validado.", { type: "success" });
            this.close();
            await this.action.doAction({ type: "ir.actions.client", tag: "reload" });
        } finally {
            this.state.saving = false;
        }
    }

    close() {
        this.stopCamera();
        this.action.doAction({ type: "ir.actions.client", tag: "history_back" });
    }
}

QrCameraScannerAction.template = "modulo_aduana_odoo.QrCameraScannerAction";
registry.category("actions").add("mx_qr_camera_scanner", QrCameraScannerAction);
