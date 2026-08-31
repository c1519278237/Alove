# 归音 Flutter App

同一套 Flutter 代码支持 Android、iOS 和 Web，并根据家庭角色进入老人端、子女端或管理员面板。

本机运行：

```powershell
& 'E:\DevTools\flutter\bin\flutter.bat' pub get
& 'E:\DevTools\flutter\bin\flutter.bat' run -d web-server --web-port 8080 --dart-define=API_BASE_URL=http://127.0.0.1:8000/api/v1
```

Android 模拟器使用 `10.0.2.2` 访问宿主机；真实手机必须把 `API_BASE_URL` 换成电脑的局域网地址。iOS 必须在 macOS/Xcode 上签名构建。
