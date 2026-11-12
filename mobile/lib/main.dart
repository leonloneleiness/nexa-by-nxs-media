import 'dart:convert';

import 'package:cupertino_ui/cupertino_ui.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

void main() => runApp(const NexaApp());

class ChatMessage {
  const ChatMessage({required this.text, required this.fromUser});
  final String text;
  final bool fromUser;
}

class NexaApp extends StatelessWidget {
  const NexaApp({super.key, this.client});
  final http.Client? client;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'NEXA',
      theme: ThemeData(
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xff19c7b1),
          brightness: Brightness.dark,
        ),
        scaffoldBackgroundColor: const Color(0xff071421),
        useMaterial3: true,
      ),
      home: NexaHomePage(client: client),
    );
  }
}

class NexaHomePage extends StatefulWidget {
  const NexaHomePage({super.key, this.client});
  final http.Client? client;

  @override
  State<NexaHomePage> createState() => _NexaHomePageState();
}

class _NexaHomePageState extends State<NexaHomePage> {
  static const _storage = FlutterSecureStorage();
  static const _endpointKey = 'nexa.endpoint';
  static const _tokenKey = 'nexa.token';
  final _input = TextEditingController();
  final _endpoint = TextEditingController();
  final _model = TextEditingController();
  final _token = TextEditingController();
  final _scroll = ScrollController();
  final List<ChatMessage> _messages = [
    const ChatMessage(
      text: 'Xin chào, tôi là NEXA. Hãy nhập yêu cầu để bắt đầu.',
      fromUser: false,
    ),
  ];
  bool _sending = false;
  late final http.Client _client = widget.client ?? http.Client();
  String _status = 'Sẵn sàng';

  @override
  void initState() {
    super.initState();
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    try {
      final endpoint = await _storage.read(key: _endpointKey);
      final token = await _storage.read(key: _tokenKey);
      final model = await _storage.read(key: 'nexa.model');
      if (!mounted) return;
      setState(() {
        if (endpoint?.isNotEmpty == true) _endpoint.text = endpoint!;
        if (token != null) _token.text = token;
        if (model != null) _model.text = model;
      });
    } catch (_) {
      if (mounted) setState(() => _status = 'Không đọc được cấu hình bảo mật.');
    }
  }

  Future<void> _saveSettings() async {
    await _storage.write(key: 'nexa.model', value: _model.text.trim());
    await _storage.write(key: _endpointKey, value: _endpoint.text.trim());
    await _storage.write(key: _tokenKey, value: _token.text.trim());
  }

  Future<void> _send() async {
    final text = _input.text.trim();
    if (text.isEmpty || _sending) return;
    final uri = Uri.tryParse(_endpoint.text.trim());
    if (uri == null ||
        uri.scheme != 'https' ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        _model.text.trim().isEmpty) {
      setState(
        () => _status = 'Cần endpoint HTTPS và tên model trong Cài đặt.',
      );
      return;
    }
    FocusManager.instance.primaryFocus?.unfocus();
    _input.clear();
    setState(() {
      _messages.add(ChatMessage(text: text, fromUser: true));
      _sending = true;
      _status = 'NEXA đang suy nghĩ…';
    });
    _jumpToEnd();
    try {
      await _saveSettings();
      final headers = <String, String>{'Content-Type': 'application/json'};
      if (_token.text.trim().isNotEmpty) {
        headers['Authorization'] = 'Bearer ${_token.text.trim()}';
      }
      final history = _messages
          .map(
            (m) => {
              'role': m.fromUser ? 'user' : 'assistant',
              'content': m.text,
            },
          )
          .toList();
      final response = await _client
          .post(
            Uri.parse(_endpoint.text.trim()),
            headers: headers,
            body: jsonEncode({
              'model': _model.text.trim(),
              'messages': history,
              'stream': false,
            }),
          )
          .timeout(const Duration(seconds: 90));
      if (response.statusCode < 200 || response.statusCode >= 300) {
        throw Exception('Máy chủ trả về HTTP ${response.statusCode}.');
      }
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      final choices = body['choices'] as List<dynamic>?;
      final content = choices?.isNotEmpty == true
          ? (choices!.first['message']?['content'] ?? choices.first['text'])
          : null;
      if (content == null || content.toString().trim().isEmpty) {
        throw Exception('Phản hồi không có nội dung.');
      }
      if (!mounted) return;
      setState(() {
        _messages.add(
          ChatMessage(text: content.toString().trim(), fromUser: false),
        );
        _status = 'Sẵn sàng';
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _messages.removeLast();
        _input.text = text;
        _status = 'Yêu cầu thất bại. Kiểm tra mạng, endpoint, token và model.';
      });
    } finally {
      if (mounted) setState(() => _sending = false);
      _jumpToEnd();
    }
  }

  void _jumpToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _showSettings() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (context) => Padding(
        padding: EdgeInsets.fromLTRB(
          20,
          20,
          20,
          MediaQuery.viewInsetsOf(context).bottom + 20,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'Kết nối NEXA',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 16),
            TextField(
              controller: _endpoint,
              decoration: const InputDecoration(
                labelText: 'Endpoint OpenAI-compatible',
                hintText: 'https://…/v1/chat/completions',
              ),
            ),
            TextField(
              controller: _model,
              decoration: const InputDecoration(
                labelText: 'Tên model của máy chủ',
              ),
            ),
            TextField(
              controller: _token,
              obscureText: true,
              decoration: const InputDecoration(
                labelText: 'Token (lưu trong Keychain)',
              ),
            ),
            const SizedBox(height: 16),
            const Text(
              'Khi gửi, nội dung hội thoại trong phiên được chuyển đến máy chủ bạn cấu hình. Lịch sử chỉ giữ trong RAM.',
            ),
            FilledButton(
              onPressed: () async {
                try {
                  await _saveSettings();
                  if (context.mounted) Navigator.pop(context);
                } catch (_) {
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Không lưu được cấu hình.')),
                    );
                  }
                }
              },
              child: const Text('Lưu cấu hình'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('NEXA'),
        actions: [
          IconButton(
            tooltip: 'Cuộc trò chuyện mới',
            onPressed: _sending
                ? null
                : () => setState(() => _messages.clear()),
            icon: const Icon(Icons.add_comment_outlined),
          ),
          IconButton(
            onPressed: _sending ? null : _showSettings,
            icon: const Icon(Icons.settings_outlined),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(18, 12, 18, 4),
              child: Row(
                children: [
                  const Icon(CupertinoIcons.sparkles, color: Color(0xff19c7b1)),
                  const SizedBox(width: 8),
                  Text(_status, style: Theme.of(context).textTheme.bodySmall),
                ],
              ),
            ),
            Expanded(
              child: ListView.builder(
                controller: _scroll,
                padding: const EdgeInsets.all(16),
                itemCount: _messages.length,
                itemBuilder: (context, index) {
                  final message = _messages[index];
                  return Align(
                    alignment: message.fromUser
                        ? Alignment.centerRight
                        : Alignment.centerLeft,
                    child: Container(
                      constraints: const BoxConstraints(maxWidth: 330),
                      margin: const EdgeInsets.only(bottom: 12),
                      padding: const EdgeInsets.all(14),
                      decoration: BoxDecoration(
                        color: message.fromUser
                            ? const Color(0xff116b70)
                            : const Color(0xff142536),
                        borderRadius: BorderRadius.circular(18),
                      ),
                      child: Text(message.text),
                    ),
                  );
                },
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _input,
                      textInputAction: TextInputAction.send,
                      onSubmitted: (_) => _send(),
                      minLines: 1,
                      maxLines: 4,
                      decoration: const InputDecoration(
                        hintText: 'Nói gì đó với NEXA…',
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.all(Radius.circular(18)),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  FloatingActionButton(
                    onPressed: _sending ? null : _send,
                    child: _sending
                        ? const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.arrow_upward),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    if (widget.client == null) _client.close();
    _input.dispose();
    _endpoint.dispose();
    _model.dispose();
    _token.dispose();
    _scroll.dispose();
    super.dispose();
  }
}
