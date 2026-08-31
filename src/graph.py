import os
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from src.schemas import MessageClassification
from src.config import get_llm, settings
from src.vector_store import (
    query_kb, 
    add_chat_message_to_archive, 
    query_chat_archive, 
    get_recent_catchup_context
)

class CopilotState(TypedDict):
    sender: str
    group_id: str
    raw_message: str
    classification: Optional[MessageClassification]
    retrieved_context: Optional[str]
    draft_response: Optional[str]
    should_reply: bool
    should_alert_prefect: bool
    prefect_alert_text: Optional[str]

llm = get_llm()
classifier_llm = llm.with_structured_output(MessageClassification)

def resolve_cohort_tag(group_id: str) -> Optional[str]:
    c1 = os.getenv("COHORT_1_GROUP_ID") or settings.COHORT_1_GROUP_ID or "120363428812662381@g.us"
    c2 = os.getenv("COHORT_2_GROUP_ID") or settings.COHORT_2_GROUP_ID or "120363406407748018@g.us"
    if c1 and group_id == c1:
        return "Cohort 1"
    elif c2 and group_id == c2:
        return "Cohort 2"
    return None

def router_node(state: CopilotState):
    msg = state["raw_message"].strip()
    group_id = state.get("group_id", "")
    is_group = group_id.endswith("@g.us")
    cohort_tag = resolve_cohort_tag(group_id) or "Cohort Group"
    
    # 1. Prefect Direct Command Check (starts with / or !)
    if msg.startswith(("/", "!")):
        parts = msg.split()
        cmd = parts[0].lower()
        args = " ".join(parts[1:]) if len(parts) > 1 else ""
        
        target_cohort = None
        if "1" in args:
            target_cohort = "Cohort 1"
        elif "2" in args:
            target_cohort = "Cohort 2"
            
        if cmd in ["/catchup", "!catchup", "/digest", "!digest"]:
            context = get_recent_catchup_context(cohort_tag=target_cohort, n_results=30)
            prompt = f"""
            You are an executive assistant summarizing missed bootcamp discussions for a busy student/prefect.
            Cohort Filter: {target_cohort or 'All Cohorts'}
            
            Recent Chat Messages & Announcements:
            {context}
            
            Generate a clean, structured WhatsApp Catch-Up Digest with:
            1. 📢 *Major Announcements & Schedule Updates*
            2. ⏰ *Assignments, Homework & Deadlines*
            3. 🔗 *Important Links, Colab Notebooks or Resources*
            4. 💡 *Key Discussion Blockers or FAQs*
            
            Keep bullet points crisp, actionable, and formatted for WhatsApp bolding (*text*).
            """
            digest = llm.invoke(prompt).content
            header = f"📋 *Bootcamp Catch-Up Digest ({target_cohort or 'All Cohorts'})*\n\n"
            return {"draft_response": header + digest, "should_reply": True, "should_alert_prefect": False}
            
        elif cmd in ["/deadlines", "!deadlines"]:
            context = query_chat_archive("deadline submission due date assignment project", cohort_tag=target_cohort, n_results=10)
            prompt = f"""
            Extract all upcoming deadlines and deliverables from these messages:
            {context}
            
            Format as a clean bulleted list for WhatsApp.
            """
            deadlines = llm.invoke(prompt).content
            return {"draft_response": f"⏰ *Upcoming Deadlines ({target_cohort or 'All Cohorts'})*\n\n{deadlines}", "should_reply": True, "should_alert_prefect": False}
            
        elif cmd in ["/search", "!search"]:
            if not args:
                return {"draft_response": "⚠️ Please provide a search term. Example: `/search homework 2`", "should_reply": True, "should_alert_prefect": False}
            results = query_chat_archive(args, cohort_tag=target_cohort, n_results=6)
            return {"draft_response": f"🔍 *Search Results for '{args}':*\n\n{results}", "should_reply": True, "should_alert_prefect": False}
            
        elif cmd in ["/ask", "!ask"]:
            if not args:
                return {"draft_response": "⚠️ Please ask a question. Example: `/ask what is a state reducer?`", "should_reply": True, "should_alert_prefect": False}
            lecture_ctx = query_kb(args, cohort_tag=target_cohort)
            chat_ctx = query_chat_archive(args, cohort_tag=target_cohort)
            combined_prompt = f"""
            You are a helpful cohort copilot answering a direct query.
            Lecture Knowledge:
            {lecture_ctx}
            
            Chat History:
            {chat_ctx}
            
            Question: {args}
            
            Provide a helpful, concise answer citing timestamps if available.
            """
            answer = llm.invoke(combined_prompt).content
            return {"draft_response": answer, "should_reply": True, "should_alert_prefect": False}

    # 2. Strict Whitelist & Privacy Check
    if is_group and not resolve_cohort_tag(group_id):
        # Ignore unwhitelisted groups
        return {
            "classification": None,
            "should_reply": False,
            "should_alert_prefect": False,
            "prefect_alert_text": None
        }
        
    if not is_group and not msg.startswith(("/", "!")):
        # Ignore regular private messages (don't archive them or auto-reply!)
        return {
            "classification": None,
            "should_reply": False,
            "should_alert_prefect": False,
            "prefect_alert_text": None
        }

    # 3. Whitelisted Cohort Message Processing & Archiving
    classify_prompt = f"""
    Classify this cohort chat message from '{state['sender']}':
    "{msg}"
    """
    classification = classifier_llm.invoke(classify_prompt)
    
    # Auto-archive to ChromaDB Chat Collection
    add_chat_message_to_archive(
        sender=state['sender'],
        message=msg,
        group_id=group_id,
        cohort_tag=cohort_tag,
        category=classification.category,
        summary=classification.summary,
        deadline=classification.extracted_deadline or ""
    )
    
    # Check for VIP Proactive Alert (Announcements & Deadlines)
    is_vip = classification.category in ["ANNOUNCEMENT", "ASSIGNMENT_DEADLINE"] or classification.is_urgent
    alert_text = None
    if is_vip:
        deadline_str = f"⏰ *Deadline:* {classification.extracted_deadline}\n" if classification.extracted_deadline else ""
        alert_text = (
            f"🚨 *[VIP ALERT: {cohort_tag}]*\n"
            f"👤 *From:* {state['sender']}\n"
            f"📌 *Category:* {classification.category}\n"
            f"📝 *Summary:* {classification.summary}\n"
            f"{deadline_str}"
            f"\n💬 *Original:* \"{msg}\""
        )
    
    # If student question in public group, draft answer
    if classification.category == "STUDENT_QUESTION":
        context = query_kb(msg, cohort_tag=cohort_tag)
        qa_prompt = f"""
        You are a helpful bootcamp teaching assistant answering a student question.
        Context from lecture materials:
        {context}
        
        Student Question:
        {msg}
        
        Provide a concise, encouraging answer citing lecture timestamps if available.
        """
        answer = llm.invoke(qa_prompt).content
        return {
            "classification": classification,
            "retrieved_context": context,
            "draft_response": answer,
            "should_reply": True,
            "should_alert_prefect": is_vip,
            "prefect_alert_text": alert_text
        }
        
    return {
        "classification": classification,
        "should_reply": False,
        "should_alert_prefect": is_vip,
        "prefect_alert_text": alert_text
    }

workflow = StateGraph(CopilotState)
workflow.add_node("process", router_node)
workflow.set_entry_point("process")
workflow.add_edge("process", END)

copilot_graph = workflow.compile()
