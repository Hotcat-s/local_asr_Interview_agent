use std::{
    io::{BufRead, BufReader, Read},
    net::{SocketAddr, TcpStream},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::Duration,
};

use serde::Serialize;
use tauri::{Emitter, Manager, RunEvent, State};

const SERVER_PORT: u16 = 17493;
const SERVER_URL: &str = "http://127.0.0.1:17493";

struct ServerState {
    child: Mutex<Option<Child>>,
    data_dir: PathBuf,
    repo_root: PathBuf,
    sidecar: Option<PathBuf>,
    starting: Mutex<bool>,
}

#[derive(Serialize, Clone)]
struct ServerInfo {
    url: String,
    running: bool,
    data_dir: String,
    mode: String,
}

#[tauri::command]
fn start_server(app: tauri::AppHandle, state: State<'_, ServerState>) -> Result<String, String> {
    let _starting = state
        .starting
        .lock()
        .map_err(|_| "sidecar lock was poisoned".to_string())?;

    if server_port_open() {
        let _ = app.emit("sidecar-status", "ready");
        return Ok(SERVER_URL.to_string());
    }

    let mut slot = state
        .child
        .lock()
        .map_err(|_| "sidecar child lock was poisoned".to_string())?;

    if let Some(child) = slot.as_mut() {
        match child.try_wait() {
            Ok(None) => return Ok(SERVER_URL.to_string()),
            Ok(Some(_)) | Err(_) => *slot = None,
        }
    }

    let (program, args) = sidecar_command(state.inner());
    let mut command = Command::new(&program);
    command
        .args(&args)
        .current_dir(&state.repo_root)
        .env("PYTHONUNBUFFERED", "1")
        .env("INTERVIEW_DATA_DIR", &state.data_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = command.spawn().map_err(|error| {
        format!(
            "无法启动 Python 边车（{}）：{error}",
            program.to_string_lossy()
        )
    })?;

    pipe_logs(&app, child.stdout.take(), "stdout");
    pipe_logs(&app, child.stderr.take(), "stderr");

    *slot = Some(child);
    let _ = app.emit("sidecar-status", "starting");
    Ok(SERVER_URL.to_string())
}

#[tauri::command]
fn stop_server(state: State<'_, ServerState>) -> Result<(), String> {
    let mut slot = state
        .child
        .lock()
        .map_err(|_| "sidecar child lock was poisoned".to_string())?;
    if let Some(mut child) = slot.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
    Ok(())
}

#[tauri::command]
fn server_info(state: State<'_, ServerState>) -> ServerInfo {
    ServerInfo {
        url: SERVER_URL.to_string(),
        running: server_port_open(),
        data_dir: state.data_dir.to_string_lossy().to_string(),
        mode: if state.sidecar.is_some() {
            "bundled".to_string()
        } else {
            "python".to_string()
        },
    }
}

#[tauri::command]
fn get_data_dir(state: State<'_, ServerState>) -> String {
    state.data_dir.to_string_lossy().to_string()
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let repo_root = repo_root();
            let data_dir = resolve_data_dir(&*app, &repo_root);
            std::fs::create_dir_all(&data_dir)?;
            let sidecar = resolve_sidecar(&*app);

            app.manage(ServerState {
                child: Mutex::new(None),
                data_dir,
                repo_root,
                sidecar,
                starting: Mutex::new(false),
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            start_server,
            stop_server,
            server_info,
            get_data_dir
        ])
        .build(tauri::generate_context!())
        .expect("failed to build the Tauri application")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app.try_state::<ServerState>() {
                    if let Ok(mut slot) = state.child.lock() {
                        if let Some(mut child) = slot.take() {
                            let _ = child.kill();
                            let _ = child.wait();
                        }
                    }
                }
            }
        });
}

fn sidecar_command(state: &ServerState) -> (PathBuf, Vec<String>) {
    let args = vec![
        "--host".to_string(),
        "127.0.0.1".to_string(),
        "--port".to_string(),
        SERVER_PORT.to_string(),
        "--data-dir".to_string(),
        state.data_dir.to_string_lossy().to_string(),
        "--parent-pid".to_string(),
        std::process::id().to_string(),
    ];

    if let Some(sidecar) = &state.sidecar {
        return (sidecar.clone(), args);
    }

    let mut python_args = vec!["-m".to_string(), "backend.main".to_string()];
    python_args.extend(args);
    (python_executable(&state.repo_root), python_args)
}

fn python_executable(repo_root: &Path) -> PathBuf {
    #[cfg(windows)]
    {
        let candidate = repo_root.join(".venv").join("Scripts").join("python.exe");
        if candidate.exists() {
            return candidate;
        }
        PathBuf::from("python")
    }

    #[cfg(not(windows))]
    {
        let candidate = repo_root.join(".venv").join("bin").join("python");
        if candidate.exists() {
            return candidate;
        }
        PathBuf::from("python3")
    }
}

fn resolve_sidecar(app: &tauri::App) -> Option<PathBuf> {
    if let Ok(value) = std::env::var("INTERVIEW_SIDECAR") {
        let candidate = PathBuf::from(value);
        if candidate.exists() {
            return Some(candidate);
        }
    }

    let resource_dir = app.path().resource_dir().ok()?;
    for name in [
        "interview-server",
        "interview-server.exe",
        "binaries/interview-server",
        "binaries/interview-server.exe",
    ] {
        let candidate = resource_dir.join(name);
        if candidate.exists() {
            return Some(candidate);
        }
    }
    None
}

fn resolve_data_dir(app: &tauri::App, repo_root: &Path) -> PathBuf {
    if let Ok(value) = std::env::var("INTERVIEW_DATA_DIR") {
        return PathBuf::from(value);
    }
    if cfg!(debug_assertions) {
        return repo_root.join("data");
    }
    app.path()
        .app_data_dir()
        .unwrap_or_else(|_| repo_root.join("data"))
}

fn repo_root() -> PathBuf {
    if let Ok(value) = std::env::var("INTERVIEW_REPO_ROOT") {
        return PathBuf::from(value);
    }
    if cfg!(debug_assertions) {
        let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        if let Some(root) = manifest.parent().and_then(Path::parent) {
            return root.to_path_buf();
        }
    }
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

fn server_port_open() -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], SERVER_PORT));
    TcpStream::connect_timeout(&address, Duration::from_millis(400)).is_ok()
}

fn pipe_logs<R>(app: &tauri::AppHandle, stream: Option<R>, channel: &'static str)
where
    R: Read + Send + 'static,
{
    let Some(stream) = stream else {
        return;
    };
    let app = app.clone();
    thread::spawn(move || {
        for line in BufReader::new(stream).lines().map_while(Result::ok) {
            let _ = app.emit("sidecar-log", format!("[{channel}] {line}"));
        }
    });
}
