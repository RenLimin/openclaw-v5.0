// wecom_ax_engine.swift
// 企业微信 / 微信 macOS Accessibility 【严格只读】采集引擎（零注入）
//
// ── 只读红线（gateway-owner 2026-11-24 明令）──────────────────────────
//  本引擎对已登录的企业微信/微信客户端【只读不写】，严禁任何发送/输入动作：
//    ✗ 禁止 CGEvent 鼠标点击/键盘事件 post
//    ✗ 禁止 AXUIElementSetAttributeValue / AXUIElementPerformAction
//    ✗ 禁止模拟键入、粘贴、回车、切换会话、点开/关闭任何东西
//  仅允许 AXUIElementCopyAttributeValue 系列只读 Get。
//  tests/test_02_readonly_guard.py 会静态扫描本文件，出现禁用 API 即测试失败。
// ─────────────────────────────────────────────────────────────────────
// 子命令（全部只读）: sessions | chat [--session <kw> 仅作标签] | snapshot | images [--with-data]
// 输出: JSON 到 stdout；诊断到 stderr
import AppKit
import Foundation
import CryptoKit

// ---------- AX 基础封装 ----------
@discardableResult
func axCopy(_ el: AXUIElement, _ name: String) -> AnyObject? {
    var v: AnyObject?
    guard AXUIElementCopyAttributeValue(el, name as CFString, &v) == .success else { return nil }
    return v
}

func axString(_ el: AXUIElement, _ name: String) -> String {
    guard let v = axCopy(el, name) else { return "" }
    if let s = v as? String { return s }
    return ""
}

func axChildren(_ el: AXUIElement) -> [AXUIElement] {
    guard let v = axCopy(el, kAXChildrenAttribute as String), let arr = v as? [AXUIElement] else { return [] }
    return arr
}

func axFrame(_ el: AXUIElement) -> NSRect? {
    guard let posVal = axCopy(el, kAXPositionAttribute as String),
          let sizeVal = axCopy(el, kAXSizeAttribute as String) else { return nil }
    let posCF = posVal as CFTypeRef
    let sizeCF = sizeVal as CFTypeRef
    guard CFGetTypeID(posCF) == AXValueGetTypeID(),
          CFGetTypeID(sizeCF) == AXValueGetTypeID() else { return nil }
    let posAX = posVal as! AXValue
    let sizeAX = sizeVal as! AXValue
    var point = CGPoint.zero
    var size = CGSize.zero
    guard AXValueGetValue(posAX, .cgPoint, &point),
          AXValueGetValue(sizeAX, .cgSize, &size) else { return nil }
    return NSRect(origin: point, size: size)
}

func walkTree(_ el: AXUIElement, _ depth: Int, _ maxDepth: Int, _ out: inout [AXUIElement]) {
    guard depth <= maxDepth else { return }
    out.append(el)
    for c in axChildren(el) { walkTree(c, depth + 1, maxDepth, &out) }
}

// ---------- 元素描述 ----------
struct TextItem {
    let role: String
    let value: String
    let x: CGFloat
    let y: CGFloat
    let w: CGFloat
    let h: CGFloat
    func json() -> [String: Any] {
        return ["role": role, "value": value,
                "x": Double(x), "y": Double(y), "w": Double(w), "h": Double(h)]
    }
}

func isStandardMainWindow(_ el: AXUIElement) -> Bool {
    axString(el, kAXSubroleAttribute as String) == (kAXStandardWindowSubrole as String)
}

// ---------- 会话列表 ----------
// 左侧列: x >= 50 且 maxX <= 350 的 AXCell
func collectSessions(_ root: AXUIElement) -> [[String: Any]] {
    var all: [AXUIElement] = []
    walkTree(root, 0, 22, &all)
    var result: [[String: Any]] = []
    for cell in all where axString(cell, kAXRoleAttribute as String) == "AXCell" {
        guard let f = axFrame(cell) else { continue }
        guard f.minX >= 50, f.maxX <= 350, f.height > 20 else { continue }
        // 选中态：AXSelected 优先，其次看子节点是否有 selected
        var selected = (axCopy(cell, kAXSelectedAttribute as String) as? Bool) ?? false
        var nodes: [AXUIElement] = []
        walkTree(cell, 0, 8, &nodes)
        if !selected {
            for n in nodes {
                if let b = axCopy(n, kAXSelectedAttribute as String) as? Bool, b {
                    selected = true; break
                }
            }
        }
        var texts: [String] = []
        for n in nodes {
            let r = axString(n, kAXRoleAttribute as String)
            guard r == "AXStaticText" || r == "AXTextArea" else { continue }
            let v = axString(n, kAXValueAttribute as String)
            if !v.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                texts.append(v)
            }
        }
        guard !texts.isEmpty else { continue }
        let name = texts[0]
        var tag = ""
        for t in texts {
            if t == "外部" || t == "部门" || t == "全员" || t == "BOT" { tag = t; break }
        }
        var unread = 0
        for t in texts {
            if t.range(of: #"^\d{1,3}$"#, options: .regularExpression) != nil {
                unread = Int(t) ?? 0
                break
            }
        }
        var lastMsg = ""
        if texts.count > 1 { lastMsg = texts[1] }
        result.append([
            "name": name, "tag": tag, "unread": unread,
            "last_msg": lastMsg, "texts": texts, "selected": selected,
            "frame": [Double(f.minX), Double(f.minY), Double(f.width), Double(f.height)],
            "is_group": name.contains("群") || tag == "部门"
        ])
    }
    result.sort { ($0["frame"] as! [Double])[1] < ($1["frame"] as! [Double])[1] }
    return result
}

// ---------- 消息区 ----------
// 右侧区: x >= 340 且 maxX <= 1250
func collectRightItems(_ root: AXUIElement) -> [TextItem] {
    var all: [AXUIElement] = []
    walkTree(root, 0, 26, &all)
    var items: [TextItem] = []
    for el in all {
        let r = axString(el, kAXRoleAttribute as String)
        guard r == "AXStaticText" || r == "AXTextArea" else { continue }
        let v = axString(el, kAXValueAttribute as String)
        guard !v.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { continue }
        guard let f = axFrame(el), f.minX >= 340, f.maxX <= 1250 else { continue }
        items.append(TextItem(role: r, value: v, x: f.minX, y: f.minY, w: f.width, h: f.height))
    }
    return items
}

func isTimeText(_ s: String) -> Bool {
    let p = #"^(\d{1,2}:\d{2}|(昨天|前天|今天)\s*\d{1,2}:\d{2}|\d{4}/\d{1,2}/\d{1,2}\s*\d{1,2}:\d{2}|\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2})$"#
    return s.range(of: p, options: .regularExpression) != nil
}

func isDateSeparator(_ s: String) -> Bool {
    let p = #"^((星期|周)[一二三四五六日]|星期[一二三四五六日]|\d{1,2}月\d{1,2}日|\d{4}年)"#
    return s.range(of: p, options: .regularExpression) != nil
}

func isSystemEvent(_ s: String) -> Bool {
    let keys = ["加入群聊", "退出了群聊", "撤回了一条消息", "邀请", "被移出群聊",
                "已成为新群主", "设置了", "开启了", "关闭了"]
    return keys.contains { s.contains($0) } && s.count < 80
}

func extractMentions(_ s: String) -> [String] {
    let p = #"@([^\s@]{1,20})"#
    guard let re = try? NSRegularExpression(pattern: p) else { return [] }
    let range = NSRange(s.startIndex..., in: s)
    return re.matches(in: s, range: range).compactMap { m in
        guard let r = Range(m.range(at: 1), in: s) else { return nil }
        return String(s[r])
    }
}

// 分组启发式: 发送者标签(短、靠左) / 内容块(宽 AXTextArea) / 时间戳 / 系统
func groupMessages(_ items: [TextItem]) -> [[String: Any]] {
    let sorted = items.sorted { $0.y < $1.y }
    var msgs: [[String: Any]] = []
    // 用显式可变结构承载当前消息，避免字典下标写回的复制语义问题
    var curSender = ""
    var curContent = ""
    var curTs = ""
    var curMentions: [String] = []
    var curItems: [[String: Any]] = []
    var hasCur = false

    func flush() {
        guard hasCur else { return }
        if !curContent.isEmpty {
            msgs.append([
                "sender": curSender, "content": curContent, "ts": curTs,
                "is_self": false, "is_system": false,
                "mentions": Array(Set(curMentions)), "items": curItems
            ])
        }
        curSender = ""; curContent = ""; curTs = ""
        curMentions = []; curItems = []; hasCur = false
    }
    func ensure(_ sender: String) {
        if !hasCur {
            curSender = sender; hasCur = true
        }
    }

    for it in sorted {
        let s = it.value
        if isDateSeparator(s) || isSystemEvent(s) {
            flush()
            msgs.append(["sender": "", "content": s, "ts": "",
                         "is_self": false, "is_system": true,
                         "mentions": [] as [String], "items": [it.json()]])
            continue
        }
        if isTimeText(s) {
            ensure("")
            curTs = s
            curItems.append(it.json())
            continue
        }
        let isSender = it.x < 450 && s.count <= 20 && !s.contains("\n")
        let isContentBlock = it.role == "AXTextArea" && it.w > 20
        if isSender && !isContentBlock {
            flush()
            ensure(s)
            curSender = s
            curItems.append(it.json())
        } else {
            ensure("")
            curContent = curContent.isEmpty ? s : curContent + "\n" + s
            curMentions.append(contentsOf: extractMentions(s))
            curItems.append(it.json())
        }
    }
    flush()
    return msgs
}

// ---------- 图片（只读提取 AXImageData）----------
// 消息区内 AXImage：frame.minX >= 340 且宽 > 4。
// AXImageData 实测为 NSArray 包装（NSArrayM），需逐层下钻取 CFData/NSData。
struct ImageItem {
    let idx: Int
    let x: CGFloat
    let y: CGFloat
    let w: CGFloat
    let h: CGFloat
    let desc: String
    let embed: String
    let png: Data?

    var sha256: String? {
        png.map { SHA256.hash(data: $0).compactMap { String(format: "%02x", $0) }.joined() }
    }
    var dims: String {
        guard let d = png, let img = NSImage(data: d) else { return "?" }
        return "\(Int(img.size.width))x\(Int(img.size.height))"
    }
    func json(includeData: Bool) -> [String: Any] {
        var o: [String: Any] = [
            "i": idx, "x": Double(x), "y": Double(y),
            "w": Double(w), "h": Double(h),
            "bytes": png?.count ?? 0,
            "desc": desc, "embed": embed,
        ]
        if let s = sha256 { o["sha256"] = s }
        o["dims"] = dims
        if includeData, let d = png { o["data_b64"] = d.base64EncodedString() }
        return o
    }
}

func collectMessageImages(_ root: AXUIElement) -> [ImageItem] {
    var all: [AXUIElement] = []
    walkTree(root, 0, 40, &all)
    var out: [ImageItem] = []
    for el in all where axString(el, kAXRoleAttribute as String) == "AXImage" {
        guard let f = axFrame(el), f.minX >= 340, f.width > 4 else { continue }
        var raw: AnyObject?
        guard AXUIElementCopyAttributeValue(el, "AXImageData" as CFString, &raw) == .success,
              let r = raw else { continue }
        var png: Data? = nil
        var cur: AnyObject? = r
        for _ in 0..<6 {
            guard let c = cur else { break }
            let cf = c as CFTypeRef
            if CFGetTypeID(cf) == CFDataGetTypeID() {
                let cfd = cf as! CFData
                let len = CFDataGetLength(cfd)
                var bytes = [UInt8](repeating: 0, count: len)
                CFDataGetBytes(cfd, CFRange(location: 0, length: len), &bytes)
                png = Data(bytes); break
            }
            if let arr = c as? [Any], let first = arr.first { cur = first as AnyObject; continue }
            if let nd = c as? NSData { png = Data(nd); break }
            break
        }
        guard let d = png, d.starts(with: Data([0x89, 0x50, 0x4E, 0x47])) else { continue }
        out.append(ImageItem(idx: out.count, x: f.minX, y: f.minY, w: f.width, h: f.height,
                            desc: axString(el, "AXDescription"),
                            embed: axString(el, "AXEmbeddedImageDescription"), png: d))
    }
    return out
}

// ---------- 应用/窗口定位 ----------
// 注：原 clickElement(...) 已按只读红线物理删除——引擎不得产生任何 UI 输入事件。
func findPid(bundleId: String) -> pid_t? {
    for app in NSRunningApplication.runningApplications(withBundleIdentifier: bundleId) {
        return app.processIdentifier
    }
    return nil
}

func emit(_ obj: Any) {
    if let data = try? JSONSerialization.data(withJSONObject: obj, options: [.prettyPrinted]),
       let s = String(data: data, encoding: .utf8) {
        print(s)
    } else {
        print("{\"error\":\"serialize_failed\"}")
    }
}

// ---------- main ----------
let args = CommandLine.arguments
guard args.count >= 2 else {
    print("Usage: wecom_ax_engine <sessions|chat|snapshot> [--pid N] [--session KW]  // strict READ-ONLY")
    exit(1)
}
let cmd = args[1]

var pid: pid_t = 0
var sessionKw = ""
var withData = false
var imagesOut = ""
var onlyMessage = false
var i = 2
while i < args.count {
    switch args[i] {
    case "--pid": if i + 1 < args.count { pid = pid_t(args[i + 1]) ?? 0 }; i += 2
    case "--session": if i + 1 < args.count { sessionKw = args[i + 1] }; i += 2
    case "--with-data": withData = true; i += 1
    case "--out": if i + 1 < args.count { imagesOut = args[i + 1] }; i += 2
    case "--only-message": onlyMessage = true; i += 1
    default: i += 1
    }
}
if pid == 0 { pid = findPid(bundleId: "com.tencent.WeWorkMac") ?? 0 }
guard pid > 0 else {
    FileHandle.standardError.write(Data("engine: 找不到企业微信进程(com.tencent.WeWorkMac)\n".utf8))
    exit(2)
}

let app = AXUIElementCreateApplication(pid)
var wins: AnyObject?
guard AXUIElementCopyAttributeValue(app, kAXWindowsAttribute as CFString, &wins) == .success,
      let winArr = wins as? [AXUIElement], !winArr.isEmpty else {
    FileHandle.standardError.write(Data("engine: 无窗口\n".utf8))
    exit(3)
}
guard let mainWin = winArr.first(where: isStandardMainWindow) ?? winArr.first else {
    FileHandle.standardError.write(Data("engine: 无主窗口\n".utf8))
    exit(3)
}

let winTitle = axString(mainWin, kAXTitleAttribute as String)
var winFrame = [0.0, 0.0, 0.0, 0.0]
if let f = axFrame(mainWin) { winFrame = [Double(f.minX), Double(f.minY), Double(f.width), Double(f.height)] }

let sessions = collectSessions(mainWin)

switch cmd {
case "sessions":
    emit(["pid": Int(pid), "count": sessions.count, "sessions": sessions])

case "chat":
    // 只读红线：不切换、不点击。--session 仅作为调用方的标签透传；
    // 实际读取的是用户当前在 UI 上打开的会话。要换会话请由人工手动点击。
    let chatItems = collectRightItems(mainWin)
    let chatMsgs = groupMessages(chatItems)
    var chatOut: [String: Any] = [
        "pid": Int(pid), "window": winTitle, "win_frame": winFrame,
        "read_only": true,
        "session_count": sessions.count,
        "note": "strict-read-only: 只采集当前打开会话，不自动切换",
        "item_count": chatItems.count, "items": chatItems.map { $0.json() },
        "message_count": chatMsgs.count, "messages": chatMsgs,
    ]
    if !sessionKw.isEmpty { chatOut["requested_session"] = sessionKw }
    emit(chatOut)

case "snapshot":
    let items = collectRightItems(mainWin)
    let msgs = groupMessages(items)
    emit(["pid": Int(pid), "window": winTitle, "read_only": true, "win_frame": winFrame,
          "session_count": sessions.count, "sessions": sessions,
          "message_count": msgs.count, "messages": msgs,
          "item_count": items.count, "items": items.map { $0.json() }])

case "images":
    // 只读提取消息区图片本体（AXImageData → PNG）。不发请求、不点击、不写客户端。
    // --out DIR：把 PNG 落到 DIR（文件名含 sha256 前缀，已存在则跳过，天然去重）；
    // --with-data：在 JSON 里附带 base64（调试用，体积大）。
    let imgsAll = collectMessageImages(mainWin)
    let imgs = onlyMessage ? imgsAll.filter { $0.x < 1300 } : imgsAll
    var written = 0
    var manifest: [[String: Any]] = []
    let outURL = imagesOut.isEmpty ? nil : URL(fileURLWithPath: imagesOut)
    if let u = outURL { try? FileManager.default.createDirectory(at: u, withIntermediateDirectories: true) }
    for im in imgs {
        var o = im.json(includeData: withData)
        if let u = outURL, let d = im.png, let s = im.sha256 {
            let name = "\(s.prefix(16))_\(im.dims).png"
            let f = u.appendingPathComponent(name)
            if !FileManager.default.fileExists(atPath: f.path) {
                if (try? d.write(to: f)) != nil { written += 1 }
            }
            o["file"] = name
        }
        manifest.append(o)
    }
    emit(["pid": Int(pid), "window": winTitle, "read_only": true,
          "image_count": imgs.count, "written": written,
          "note": "strict-read-only: 仅读取当前打开会话内 AXImage.AXImageData",
          "images": manifest])

default:
    emit(["error": "unknown_command", "cmd": cmd])
    exit(1)
}
