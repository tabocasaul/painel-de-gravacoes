package br.local.lentes;

import android.app.Activity;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Matrix;
import android.graphics.RectF;
import android.graphics.SurfaceTexture;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.params.OutputConfiguration;
import android.hardware.camera2.params.SessionConfiguration;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.util.Range;
import android.util.Size;
import android.util.SizeF;
import android.view.Gravity;
import android.view.Surface;
import android.view.TextureView;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.Executor;

/**
 * Visualizador de lentes via Camera2.
 *
 * Abre a camera logica traseira e permite alternar entre:
 *  - a propria logica (com zoom 1.0x ou no minimo, que faz o HAL cair na ultra-wide)
 *  - cada camera fisica, via OutputConfiguration.setPhysicalCameraId()
 */
public class MainActivity extends Activity {

    private static final int REQ_CAM = 42;

    private TextureView texture;
    private TextView info;
    private LinearLayout buttonBar;
    private TextView extra;
    private String sizesDisponiveis = "";
    /** ajuste manual de rotacao, somado ao SENSOR_ORIENTATION. */
    private int rotExtra = 0;
    /** true = preenche a area cortando o excesso; false = cabe inteiro. */
    private boolean preencher = true;

    private CameraManager cm;
    private CameraDevice device;
    private CameraCaptureSession session;
    private HandlerThread bgThread;
    private Handler bg;
    private Executor exec;

    private String logicalId = null;   // traseira
    private String frontId = null;     // frontal (a que recebe o video)
    private final List<String> physicalIds = new ArrayList<>();

    /** camera atualmente aberta. */
    private String openId = null;
    private int sensorOrientation = 90;

    /** null = usa a logica; senao, o id da fisica a exibir. */
    private String currentPhysical = null;
    private float zoom = 1f;
    private Range<Float> zoomRange = null;
    private Size previewSize = new Size(1280, 720);

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        cm = (CameraManager) getSystemService(CAMERA_SERVICE);

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.BLACK);

        info = new TextView(this);
        info.setTextColor(Color.WHITE);
        info.setTextSize(12f);
        info.setPadding(24, 24, 24, 16);
        info.setText("iniciando...");
        root.addView(info, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        extra = new TextView(this);
        extra.setTextColor(Color.YELLOW);
        extra.setTextSize(13f);
        extra.setPadding(24, 0, 24, 16);
        root.addView(extra, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        FrameLayout holder = new FrameLayout(this);
        holder.setBackgroundColor(Color.rgb(18, 18, 18));
        texture = new TextureView(this);
        holder.addView(texture, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT, Gravity.CENTER));
        root.addView(holder, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        buttonBar = new LinearLayout(this);
        buttonBar.setOrientation(LinearLayout.HORIZONTAL);
        HorizontalScrollView scroll = new HorizontalScrollView(this);
        scroll.addView(buttonBar);
        root.addView(scroll, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        setContentView(root);

        if (checkSelfPermission(android.Manifest.permission.CAMERA)
                != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{android.Manifest.permission.CAMERA}, REQ_CAM);
        } else {
            discover();
        }
    }

    @Override
    public void onRequestPermissionsResult(int req, String[] p, int[] r) {
        if (req == REQ_CAM && r.length > 0 && r[0] == PackageManager.PERMISSION_GRANTED) {
            discover();
        } else {
            info.setText("permissao de camera negada");
        }
    }

    // ---------------------------------------------------------------- descoberta

    /** Acha a logica traseira, lista as fisicas e monta os botoes. */
    private void discover() {
        StringBuilder sb = new StringBuilder();
        try {
            for (String id : cm.getCameraIdList()) {
                CameraCharacteristics c = cm.getCameraCharacteristics(id);
                Integer facing = c.get(CameraCharacteristics.LENS_FACING);
                boolean back = facing != null && facing == CameraCharacteristics.LENS_FACING_BACK;
                if (back && logicalId == null) {
                    logicalId = id;
                    physicalIds.addAll(c.getPhysicalCameraIds());
                    Collections.sort(physicalIds);
                    zoomRange = c.get(CameraCharacteristics.CONTROL_ZOOM_RATIO_RANGE);
                } else if (!back && frontId == null) {
                    frontId = id;
                }
                sb.append(back ? "traseira" : "frontal").append(" id=").append(id)
                        .append("  ").append(describe(c)).append("\n");
            }
        } catch (CameraAccessException e) {
            info.setText("erro: " + e.getMessage());
            return;
        }

        if (logicalId == null) {
            info.setText("nenhuma camera traseira encontrada");
            return;
        }

        for (String p : physicalIds) {
            try {
                sb.append("   fisica ").append(p).append("  ")
                        .append(describe(cm.getCameraCharacteristics(p))).append("\n");
            } catch (CameraAccessException ignored) {
            }
        }
        if (physicalIds.isEmpty()) {
            sb.append("   (sem cameras fisicas: nao e multi-camera logica)\n");
        }
        info.setText(sb.toString().trim());

        buildButtons();
        startBg();
        trocarCamera(logicalId);
    }

    /** Focal, sensor e FOV diagonal calculado — e o que o Minute usa pra achar a ultra-wide. */
    private String describe(CameraCharacteristics c) {
        float[] focals = c.get(CameraCharacteristics.LENS_INFO_AVAILABLE_FOCAL_LENGTHS);
        SizeF sensor = c.get(CameraCharacteristics.SENSOR_INFO_PHYSICAL_SIZE);
        if (focals == null || focals.length == 0 || sensor == null) return "(sem dados)";
        double diag = Math.hypot(sensor.getWidth(), sensor.getHeight());
        double fov = 2 * Math.toDegrees(Math.atan(diag / (2 * focals[0])));
        return String.format("focal %.2fmm  sensor %.2fx%.2f  FOV %.1f°",
                focals[0], sensor.getWidth(), sensor.getHeight(), fov);
    }

    private void buildButtons() {
        addButton("Traseira 1.0x", v -> {
            currentPhysical = null;
            zoom = 1f;
            trocarCamera(logicalId);
        });
        if (zoomRange != null && zoomRange.getLower() < 1f) {
            final float min = zoomRange.getLower();
            addButton(String.format("Traseira %.2fx", min), v -> {
                currentPhysical = null;
                zoom = min;
                trocarCamera(logicalId);
            });
        }
        for (final String p : physicalIds) {
            addButton("Fisica " + p, v -> {
                currentPhysical = p;
                zoom = 1f;
                trocarCamera(logicalId);
            });
        }
        addButton("Cheio/Ajustar", v -> {
            preencher = !preencher;
            applyTransform(texture.getWidth(), texture.getHeight());
        });
        addButton("Girar 90", v -> {
            rotExtra = (rotExtra + 90) % 360;
            applyTransform(texture.getWidth(), texture.getHeight());
        });
        if (frontId != null) {
            addButton("FRONTAL (video)", v -> {
                currentPhysical = null;
                zoom = 1f;
                trocarCamera(frontId);
            });
        }
    }

    private void addButton(String label, View.OnClickListener l) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setOnClickListener(l);
        buttonBar.addView(b);
    }

    // ---------------------------------------------------------------- camera

    private void startBg() {
        bgThread = new HandlerThread("cam");
        bgThread.start();
        bg = new Handler(bgThread.getLooper());
        exec = command -> bg.post(command);
    }

    /** Fecha a camera atual (se for outra) e abre a pedida. */
    private void trocarCamera(String id) {
        if (id == null) return;
        if (id.equals(openId) && device != null) {
            restartSession();
            return;
        }
        if (session != null) { session.close(); session = null; }
        if (device != null) { device.close(); device = null; }
        openCamera(id);
    }

    private void openCamera(String id) {
        openId = id;
        try {
            Integer o = cm.getCameraCharacteristics(id)
                    .get(CameraCharacteristics.SENSOR_ORIENTATION);
            sensorOrientation = o != null ? o : 90;
        } catch (CameraAccessException ignored) {
        }
        try {
            cm.openCamera(id, new CameraDevice.StateCallback() {
                @Override public void onOpened(CameraDevice d) {
                    device = d;
                    runOnUiThread(MainActivity.this::restartSession);
                }
                @Override public void onDisconnected(CameraDevice d) { d.close(); device = null; }
                @Override public void onError(CameraDevice d, int err) {
                    d.close(); device = null;
                    runOnUiThread(() -> toast("erro ao abrir camera: " + err));
                }
            }, bg);
        } catch (CameraAccessException | SecurityException e) {
            toast("openCamera falhou: " + e.getMessage());
        }
    }

    /**
     * Recria a sessao. Quando currentPhysical != null, o stream e amarrado
     * aquela lente via OutputConfiguration.setPhysicalCameraId().
     */
    private void restartSession() {
        if (device == null) return;
        if (!texture.isAvailable()) {
            texture.setSurfaceTextureListener(new TextureView.SurfaceTextureListener() {
                @Override public void onSurfaceTextureAvailable(SurfaceTexture s, int w, int h) {
                    restartSession();
                }
                @Override public void onSurfaceTextureSizeChanged(SurfaceTexture s, int w, int h) {
                    applyTransform(w, h);
                }
                @Override public boolean onSurfaceTextureDestroyed(SurfaceTexture s) { return true; }
                @Override public void onSurfaceTextureUpdated(SurfaceTexture s) { }
            });
            return;
        }

        if (session != null) {
            session.close();
            session = null;
        }

        previewSize = pickSize(currentPhysical == null ? openId : currentPhysical);

        SurfaceTexture st = texture.getSurfaceTexture();
        st.setDefaultBufferSize(previewSize.getWidth(), previewSize.getHeight());
        applyTransform(texture.getWidth(), texture.getHeight());
        final Surface surface = new Surface(st);

        OutputConfiguration oc = new OutputConfiguration(surface);
        if (currentPhysical != null) oc.setPhysicalCameraId(currentPhysical);

        SessionConfiguration sc = new SessionConfiguration(
                SessionConfiguration.SESSION_REGULAR,
                Arrays.asList(oc), exec,
                new CameraCaptureSession.StateCallback() {
                    @Override public void onConfigured(CameraCaptureSession s) {
                        session = s;
                        try {
                            CaptureRequest.Builder rb =
                                    device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW);
                            rb.addTarget(surface);
                            if (currentPhysical == null && zoomRange != null) {
                                rb.set(CaptureRequest.CONTROL_ZOOM_RATIO, zoom);
                            }
                            s.setRepeatingRequest(rb.build(), null, bg);
                            runOnUiThread(() -> toast(currentPhysical == null
                                    ? String.format("camera %s @ %.2fx  (sensor %d graus)",
                                                    openId, zoom, sensorOrientation)
                                    : "fisica " + currentPhysical));
                        } catch (CameraAccessException e) {
                            runOnUiThread(() -> toast("request falhou: " + e.getMessage()));
                        }
                    }
                    @Override public void onConfigureFailed(CameraCaptureSession s) {
                        runOnUiThread(() -> toast("sessao falhou"
                                + (currentPhysical != null ? " na fisica " + currentPhysical : "")));
                    }
                });

        try {
            device.createCaptureSession(sc);
        } catch (CameraAccessException e) {
            toast("createCaptureSession: " + e.getMessage());
        }
    }

    /**
     * Escolhe o stream 16:9 mais alto ate 1080p.
     *
     * A camera do emulador tambem anuncia tamanhos 4:3 (1280x960). Pegar o de
     * maior area cai no 4:3 e o video 16:9 entra com tarja preta. Girado pelo
     * sensor, um 16:9 vira 9:16 e preenche a tela inteira.
     */
    private Size pickSize(String id) {
        try {
            StreamConfigurationMap map = cm.getCameraCharacteristics(id)
                    .get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
            if (map == null) return previewSize;

            final double alvo = 16.0 / 9.0;
            Size melhor = null;
            double melhorDif = Double.MAX_VALUE;
            StringBuilder disp = new StringBuilder();

            for (Size sz : map.getOutputSizes(SurfaceTexture.class)) {
                if (sz.getWidth() > 1920 || sz.getHeight() > 1080) continue;
                disp.append(sz.getWidth()).append('x').append(sz.getHeight()).append(' ');
                double dif = Math.abs(sz.getWidth() / (double) sz.getHeight() - alvo);
                boolean melhorAspecto = dif < melhorDif - 0.01;
                boolean mesmoAspectoMaior = Math.abs(dif - melhorDif) <= 0.01
                        && melhor != null
                        && (long) sz.getWidth() * sz.getHeight()
                           > (long) melhor.getWidth() * melhor.getHeight();
                if (melhor == null || melhorAspecto || mesmoAspectoMaior) {
                    melhor = sz;
                    melhorDif = dif;
                }
            }
            sizesDisponiveis = disp.toString().trim();
            return melhor != null ? melhor : previewSize;
        } catch (CameraAccessException e) {
            return previewSize;
        }
    }

    private void applyTransform(int viewW, int viewH) {
        if (viewW == 0 || viewH == 0) return;

        // A TextureView primeiro estica o buffer ate o tamanho da view; a matriz
        // atua depois, em coordenadas de view. Entao a gente desfaz o esticamento
        // e gira, deixando a imagem com o aspecto certo e centralizada.
        float bw = previewSize.getWidth();
        float bh = previewSize.getHeight();
        int rot = ((sensorOrientation + rotExtra) % 360 + 360) % 360;

        // escala uniforme para caber: com 90/270 os eixos trocam
        float a, b;
        if (rot % 180 == 90) {          // girado: os eixos trocam
            a = viewW / bh;
            b = viewH / bw;
        } else {
            a = viewW / bw;
            b = viewH / bh;
        }
        float s = preencher ? Math.max(a, b) : Math.min(a, b);

        Matrix m = new Matrix();
        float cx = viewW / 2f, cy = viewH / 2f;
        m.postScale(bw * s / viewW, bh * s / viewH, cx, cy);
        m.postRotate(rot, cx, cy);
        texture.setTransform(m);

        int finalW = (int) ((rot % 180 == 90 ? bh : bw) * s);
        int finalH = (int) ((rot % 180 == 90 ? bw : bh) * s);
        final String txt = String.format(
                "buffer %dx%d  sensor %d°  ->  tela %dx%d%ndisponiveis: %s",
                (int) bw, (int) bh, rot, finalW, finalH, sizesDisponiveis);
        runOnUiThread(() -> extra.setText(txt));
    }

    private void toast(String s) {
        Toast.makeText(this, s, Toast.LENGTH_SHORT).show();
    }

    @Override
    protected void onDestroy() {
        if (session != null) session.close();
        if (device != null) device.close();
        if (bgThread != null) bgThread.quitSafely();
        super.onDestroy();
    }
}
