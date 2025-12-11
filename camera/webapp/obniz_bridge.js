const Obniz = require("obniz");
const readline = require("readline");

// コマンドライン引数からObniz IDを取得
const OBNIZ_ID = process.argv[2];

if (!OBNIZ_ID) {
    console.error("Usage: node obniz_bridge.js <OBNIZ_ID>");
    process.exit(1);
}

console.log(`Connecting to Obniz ${OBNIZ_ID}...`);
const obniz = new Obniz(OBNIZ_ID);
let servo = null;

// Obniz接続処理
obniz.onconnect = async function () {
    console.log("Obniz connected");
    // サーボモーター初期化 (Signal:0, VCC:1, GND:2)
    servo = obniz.wired("ServoMotor", { signal: 0, vcc: 1, gnd: 2 });
    // 初期位置へ
    servo.angle(90);
    console.log("Servo initialized to 90 deg");
};

obniz.onclose = async function () {
    console.error("Obniz connection closed");
    // 再接続はライブラリが自動で試行するが、必要ならここで処理
};

// 標準入力の読み込み設定
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false
});

// JSONコマンドの受信
rl.on("line", (line) => {
    try {
        const cmd = JSON.parse(line);
        if (typeof cmd.angle === "number") {
            if (servo) {
                console.log(`Moving servo to ${cmd.angle}`);
                servo.angle(cmd.angle);
            } else {
                console.error("Servo not ready");
            }
        }
    } catch (e) {
        console.error("Invalid JSON:", line);
    }
});

// プロセス終了時のクリーンアップ
// プロセス終了時のクリーンアップ
const cleanup = () => {
    if (obniz) {
        obniz.close();
    }
    process.exit();
};

process.on("SIGINT", cleanup);
process.on("SIGTERM", cleanup);
