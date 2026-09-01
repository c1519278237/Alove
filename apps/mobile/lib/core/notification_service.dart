import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:timezone/data/latest.dart' as tz;
import 'package:timezone/timezone.dart' as tz;

class NotificationService {
  NotificationService._();

  static final instance = NotificationService._();
  final _plugin = FlutterLocalNotificationsPlugin();
  bool _ready = false;
  bool _permissionAsked = false;

  Future<void> initialize() async {
    if (kIsWeb || _ready) return;
    tz.initializeTimeZones();
    final zone = DateTime.now().timeZoneName;
    if (tz.timeZoneDatabase.locations.containsKey(zone)) {
      tz.setLocalLocation(tz.getLocation(zone));
    } else {
      tz.setLocalLocation(tz.getLocation('Asia/Shanghai'));
    }
    await _plugin.initialize(
      const InitializationSettings(
        android: AndroidInitializationSettings('@mipmap/ic_launcher'),
        iOS: DarwinInitializationSettings(
          requestAlertPermission: false,
          requestBadgePermission: false,
          requestSoundPermission: false,
        ),
      ),
    );
    _ready = true;
  }

  Future<void> syncReminders(List<Map<String, dynamic>> reminders) async {
    if (kIsWeb || !_ready) return;
    if (!_permissionAsked) {
      await _plugin
          .resolvePlatformSpecificImplementation<
              AndroidFlutterLocalNotificationsPlugin>()
          ?.requestNotificationsPermission();
      await _plugin
          .resolvePlatformSpecificImplementation<
              IOSFlutterLocalNotificationsPlugin>()
          ?.requestPermissions(alert: true, badge: true, sound: true);
      _permissionAsked = true;
    }
    for (final reminder in reminders.where((item) => item['status'] == 'active')) {
      await scheduleReminder(reminder);
    }
  }

  Future<void> scheduleReminder(Map<String, dynamic> reminder) async {
    final rule = reminder['schedule_rule']?.toString() ?? '';
    final body = reminder['content']?.toString() ?? '您有一条家庭提醒';
    final id = (reminder['id']?.toString() ?? body).hashCode & 0x7fffffff;
    tz.TZDateTime? when;
    DateTimeComponents? repeat;
    if (rule.startsWith('once:')) {
      final parsed = DateTime.tryParse(rule.substring(5));
      if (parsed != null) when = tz.TZDateTime.from(parsed.toLocal(), tz.local);
    } else {
      final match = RegExp(r'(\d{1,2}):(\d{2})').firstMatch(rule);
      if (match != null) {
        final hour = int.parse(match.group(1)!);
        final minute = int.parse(match.group(2)!);
        final now = tz.TZDateTime.now(tz.local);
        when = tz.TZDateTime(tz.local, now.year, now.month, now.day, hour, minute);
        if (!when.isAfter(now)) when = when.add(const Duration(days: 1));
        if (rule.contains('每天')) repeat = DateTimeComponents.time;
      }
    }
    if (when == null || !when.isAfter(tz.TZDateTime.now(tz.local))) return;
    await _plugin.zonedSchedule(
      id,
      '归音家庭提醒',
      body,
      when,
      const NotificationDetails(
        android: AndroidNotificationDetails(
          'family_reminders',
          '家庭提醒',
          channelDescription: '子女与老人共同确认的生活提醒',
          importance: Importance.high,
          priority: Priority.high,
        ),
        iOS: DarwinNotificationDetails(),
      ),
      androidScheduleMode: AndroidScheduleMode.inexactAllowWhileIdle,
      matchDateTimeComponents: repeat,
    );
  }
}
