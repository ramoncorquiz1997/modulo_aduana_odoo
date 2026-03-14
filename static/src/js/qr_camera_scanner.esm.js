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
            fallbackActive: false,
        });
        this.stream = null;
        this.detector = null;
        this.autoSaveTimer = null;
        this.lastResolvedModel = null;
        this.lastResolvedResId = null;
        this.params = this.props.action.params || {};
        onMounted(async () => {
            await this.startCamera();
        });
        onWillUnmount(() => {
            if (this.autoSaveTimer) {
                clearTimeout(this.autoSaveTimer);
                this.autoSaveTimer = null;
            }
            this.stopCamera();
        });
    }

    _getModelAndResId() {
        const action = this.props.action || {};
        const params = this.params || {};
        const ctx = action.context || {};
        const model =
            params.model ||
            params.res_model ||
            action.res_model ||
            ctx.active_model ||
            false;
        const resIdRaw =
            params.resId ||
            params.res_id ||
            action.res_id ||
            ctx.active_id ||
            false;
        const resId = Number(resIdRaw) || false;
        const finalModel = model || this.lastResolvedModel || false;
        const finalResId = resId || this.lastResolvedResId || false;
        return { model: finalModel, resId: finalResId };
    }

    async _ensureTargetRecord() {
        let { model, resId } = this._getModelAndResId();
        if (model && resId) {
            this.lastResolvedModel = model;
            this.lastResolvedResId = resId;
            return { model, resId };
        }

        const action = this.props.action || {};
        const ctx = action.context || {};

        // If scanner was opened from an unsaved gafete line, bootstrap it with default_chofer_id.
        if (model === "mx.anam.gafete" || !model) {
            const defaultChoferId = Number(ctx.default_chofer_id || this.params.default_chofer_id || 0) || false;
            if (defaultChoferId) {
                const createdId = await this.orm.create("mx.anam.gafete", [{ chofer_id: defaultChoferId, active: false }]);
                model = "mx.anam.gafete";
                resId = Number(createdId) || false;
            }
        }

        // Fallback for partner actions where active_id is present in context.
        if ((!model || !resId) && (ctx.active_model || this.params.model) === "res.partner") {
            model = "res.partner";
            resId = Number(ctx.active_id || this.params.resId || this.params.res_id || 0) || false;
        }

        if (model && resId) {
            this.lastResolvedModel = model;
            this.lastResolvedResId = resId;
        }
        return { model: model || false, resId: resId || false };
    }

    async startCamera() {
        this.state.error = "";
        this.state.fallbackActive = false;
        if (!navigator.mediaDevices?.getUserMedia) {
            this.state.error = "Este navegador no soporta acceso a camara.";
            return;
        }
        try {
            this.stream = await navigator.mediaDevices.getUserMedia({
                video: {
                    facingMode: { ideal: "environment" },
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                },
                audio: false,
            });
            const video = this.videoRef.el;
            video.setAttribute("playsinline", "true");
            video.setAttribute("webkit-playsinline", "true");
            video.muted = true;
            video.srcObject = this.stream;
            await new Promise((resolve) => {
                const done = () => resolve();
                video.onloadedmetadata = done;
                setTimeout(done, 1200);
            });
            await video.play();

            this.state.scanning = true;
            if (this.state.supported) {
                const supportedFormats = await window.BarcodeDetector.getSupportedFormats();
                if (!supportedFormats.includes("qr_code")) {
                    this.state.error = "Detector QR local no disponible. Activando fallback servidor...";
                    await this.startServerFallbackLoop();
                    return;
                }
                this.detector = new window.BarcodeDetector({ formats: ["qr_code"] });
                this.scanLoop();
            } else {
                this.state.error = "BarcodeDetector no disponible. Activando fallback servidor...";
                await this.startServerFallbackLoop();
            }
        } catch (err) {
            this.state.error = `No fue posible abrir la camara: ${err.message || err}`;
        }
    }

    stopCamera() {
        this.state.scanning = false;
        if (this.autoSaveTimer) {
            clearTimeout(this.autoSaveTimer);
            this.autoSaveTimer = null;
        }
        if (this.stream) {
            this.stream.getTracks().forEach((t) => t.stop());
            this.stream = null;
        }
    }

    _looksLikeQrUrl(value) {
        const txt = (value || "").trim();
        return /^https?:\/\//i.test(txt) && txt.length > 20;
    }

    _scheduleAutoSave() {
        if (this.autoSaveTimer) {
            clearTimeout(this.autoSaveTimer);
        }
        this.autoSaveTimer = setTimeout(async () => {
            if (this.state.saving) {
                return;
            }
            if (!this._looksLikeQrUrl(this.state.result)) {
                return;
            }
            await this.useResult();
        }, 250);
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
                        this._scheduleAutoSave();
                        return;
                    }
                }
            } catch (_err) {
                // transient error
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
        const maxWidth = 960;
        const scale = Math.min(1, maxWidth / video.videoWidth);
        canvas.width = Math.max(320, Math.floor(video.videoWidth * scale));
        canvas.height = Math.max(240, Math.floor(video.videoHeight * scale));
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", 0.6);
    }

    async startServerFallbackLoop() {
        const { model, resId } = await this._ensureTargetRecord();
        if (!model || !resId) {
            this.state.error = "No se puede usar fallback sin modelo y registro. Guarda el registro y vuelve a abrir el escaner.";
            return;
        }
        this.lastResolvedModel = model;
        this.lastResolvedResId = resId;

        this.state.fallbackActive = true;
        try {
            const status = await this.orm.call(model, "action_qr_decoder_status", [[resId]]);
            if (!(status && status.ready)) {
                this.state.error = `Fallback servidor no disponible: ${status?.message || "decoder no configurado"}.`;
                return;
            }
        } catch (err) {
            this.state.error = `No se pudo inicializar fallback servidor: ${err.message || err}`;
            return;
        }

        let errorCount = 0;
        while (this.state.scanning) {
            try {
                const imageData = this._captureFrameDataUrl();
                if (imageData) {
                    const decoded = await this.orm.call(model, "action_decode_qr_image_from_camera", [[resId], imageData]);
                    if (decoded && String(decoded).trim()) {
                        this.state.result = String(decoded).trim();
                        this.stopCamera();
                        this._scheduleAutoSave();
                        return;
                    }
                }
                errorCount = 0;
            } catch (err) {
                errorCount += 1;
                if (errorCount >= 3) {
                    this.state.error = `Fallback activo sin lectura QR (${err.message || err}).`;
                }
            }
            await sleep(600);
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
        const { model, resId } = await this._ensureTargetRecord();
        if (!model || !resId) {
            this.notification.add("Guarda primero el registro y vuelve a abrir el escaner.", { type: "danger" });
            return;
        }
        this.state.saving = true;
        try {
            await this.orm.call(model, "action_set_qr_url_from_camera", [[resId], qrValue], { auto_validate: true });
            this.notification.add("QR detectado y guardado.", { type: "success" });
            this.stopCamera();
            await this._openTargetAfterSave(model, resId);
        } catch (err) {
            const msg = err?.message || err?.data?.message || String(err);
            this.state.error = `Error al guardar QR: ${msg}`;
            this.notification.add(`Error al guardar QR: ${msg}`, { type: "danger" });
        } finally {
            this.state.saving = false;
        }
    }

    async _openTargetAfterSave(model, resId) {
        let targetModel = model;
        let targetId = resId;

        if (model === "mx.anam.gafete") {
            const data = await this.orm.read(model, [resId], ["chofer_id"]);
            const chofer = data && data.length ? data[0].chofer_id : false;
            if (chofer && chofer[0]) {
                targetModel = "res.partner";
                targetId = chofer[0];
            }
        }

        if (targetModel && targetId) {
            await this.action.doAction({
                type: "ir.actions.act_window",
                res_model: targetModel,
                res_id: targetId,
                views: [[false, "form"]],
                view_mode: "form",
                target: "current",
            });
            return;
        }

        await this.action.doAction({ type: "ir.actions.client", tag: "reload" });
    }

    async close() {
        this.stopCamera();
        const { model, resId } = this._getModelAndResId();
        if (model && resId) {
            await this._openTargetAfterSave(model, resId);
            return;
        }
        await this.action.doAction({ type: "ir.actions.client", tag: "reload" });
    }

    onResultInput() {
        this._scheduleAutoSave();
    }
}

QrCameraScannerAction.template = "modulo_aduana_odoo.QrCameraScannerAction";
registry.category("actions").add("mx_qr_camera_scanner", QrCameraScannerAction);
