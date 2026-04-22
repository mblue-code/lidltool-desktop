import { z } from "zod";

import { apiClient } from "@/lib/api-client";

const NotificationSchema = z.object({
  id: z.string(),
  user_id: z.string(),
  kind: z.string(),
  severity: z.string(),
  title: z.string(),
  body: z.string(),
  href: z.string().nullable(),
  unread: z.boolean(),
  occurred_at: z.string(),
  read_at: z.string().nullable(),
  metadata_json: z.record(z.string(), z.unknown()).nullable().optional(),
  created_at: z.string(),
  updated_at: z.string()
});

const NotificationListSchema = z.object({
  count: z.number(),
  unread_count: z.number(),
  items: z.array(NotificationSchema)
});

const NotificationsMarkAllReadSchema = z.object({
  updated: z.number()
});

export type AppNotification = z.infer<typeof NotificationSchema>;
export type NotificationList = z.infer<typeof NotificationListSchema>;

export async function fetchNotifications(limit = 8): Promise<NotificationList> {
  return apiClient.get("/api/v1/notifications", NotificationListSchema, { limit });
}

export async function updateNotificationReadState(
  notificationId: string,
  unread: boolean
): Promise<AppNotification> {
  return apiClient.patch(`/api/v1/notifications/${notificationId}`, NotificationSchema, { unread });
}

export async function markAllNotificationsRead(): Promise<z.infer<typeof NotificationsMarkAllReadSchema>> {
  return apiClient.post("/api/v1/notifications/mark-all-read", NotificationsMarkAllReadSchema);
}
