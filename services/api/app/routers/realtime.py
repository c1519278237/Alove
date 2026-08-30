from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..database import SessionLocal
from ..deps import get_user_from_token
from ..errors import AppError
from .conversations import execute_chat_turn, require_owned_conversation

router = APIRouter(tags=["realtime"])


@router.websocket("/realtime/conversations/{conversation_id}")
async def realtime_conversation(websocket: WebSocket, conversation_id: str) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4401, reason="token required")
        return
    db = SessionLocal()
    try:
        try:
            user = get_user_from_token(token, db)
            conversation = require_owned_conversation(db, conversation_id, user.id)
        except AppError as exc:
            await websocket.close(code=4403, reason=exc.code)
            return
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "session.ready",
                "session_id": conversation.id,
                "ai_identity": "我是归音AI助手，不是真实家人",
                "audio_supported": False,
            }
        )
        while True:
            event = await websocket.receive_json()
            event_type = event.get("type")
            if event_type == "session.start":
                await websocket.send_json({"type": "session.ready", "session_id": conversation.id})
            elif event_type in {"text.input", "transcript.commit"}:
                text = str(event.get("text", "")).strip()
                if not text:
                    await websocket.send_json(
                        {"type": "error", "code": "EMPTY_TEXT", "message": "内容不能为空"}
                    )
                    continue
                user_message, assistant_message, result = await execute_chat_turn(
                    db, conversation=conversation, text=text
                )
                await websocket.send_json({"type": "asr.final", "text": text})
                await websocket.send_json({"type": "assistant.text.delta", "text": result.text})
                if result.safety_level != "low":
                    await websocket.send_json(
                        {
                            "type": "safety.notice",
                            "level": result.safety_level,
                            "labels": result.labels,
                            "message": "本轮触发安全提示",
                        }
                    )
                await websocket.send_json(
                    {
                        "type": "response.completed",
                        "message_id": assistant_message.id,
                        "user_message_id": user_message.id,
                    }
                )
            elif event_type == "audio.chunk":
                await websocket.send_json({"type": "audio.ack", "sequence": event.get("sequence")})
            elif event_type == "audio.commit":
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "ASR_NOT_CONFIGURED",
                        "message": "当前开发版本尚未配置语音识别供应商，请发送 transcript.commit。",
                    }
                )
            elif event_type == "session.end":
                await websocket.close(code=1000)
                return
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "code": "UNKNOWN_EVENT",
                        "message": "不支持的实时事件类型",
                    }
                )
    except WebSocketDisconnect:
        return
    finally:
        db.close()
