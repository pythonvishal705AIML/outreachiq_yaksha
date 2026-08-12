import re
from django.db.models import Q
from ..models import AIPromptTemplate, AIPromptTemplateVersion


class AIPromptTemplateService:
    """All DB logic for AI Prompt Templates. No HTTP/request logic here."""

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _next_version_number(template):
        last = template.versions.order_by("-version_number").first()
        return (last.version_number + 1) if last else 1

    @staticmethod
    def _snapshot(template, version_number):
        """Save current template state as a version snapshot."""
        AIPromptTemplateVersion.objects.create(
            template=template,
            version_number=version_number,
            name=template.name,
            description=template.description,
            category=template.category,
            template_text=template.template_text,
            variables=template.variables,
            model_name=template.model_name,
            temperature=template.temperature,
            max_tokens=template.max_tokens,
        )

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #

    @staticmethod
    def list_templates(org_id=None, category=None):
        qs = AIPromptTemplate.objects.filter(is_active=True)
        if org_id:
            qs = qs.filter(Q(org_id=org_id) | Q(is_default=True))
        else:
            qs = qs.filter(is_default=True)
        if category:
            qs = qs.filter(category=category)
        data = list(qs.values(
            "id", "org_id", "created_by", "name", "description",
            "category", "template_text", "variables",
            "is_active", "is_default",
            "model_name", "temperature", "max_tokens",
            "created_at", "updated_at",
        ))
        return {"results": data, "count": len(data)}

    @staticmethod
    def create_template(data):
        name          = (data.get("name") or "").strip()
        template_text = (data.get("template_text") or "").strip()
        if not name:
            raise ValueError("name is required")
        if not template_text:
            raise ValueError("template_text is required")
        category = data.get("category", "custom")
        valid = [c[0] for c in AIPromptTemplate.CATEGORY_CHOICES]
        if category not in valid:
            raise ValueError(f"category must be one of {valid}")
        t = AIPromptTemplate.objects.create(
            org_id        = data.get("org_id"),
            created_by    = data.get("created_by"),
            name          = name,
            description   = data.get("description", ""),
            category      = category,
            template_text = template_text,
            variables     = data.get("variables", []),
            model_name    = data.get("model_name", "gpt-4o-mini"),
            temperature   = data.get("temperature", 0.7),
            max_tokens    = data.get("max_tokens", 500),
        )
        # Snapshot v1 immediately so history starts from creation
        AIPromptTemplateService._snapshot(t, version_number=1)
        return {
            "id": str(t.id), "name": t.name, "category": t.category,
            "description": t.description, "template_text": t.template_text,
            "variables": t.variables, "is_default": t.is_default,
            "org_id": t.org_id,
            "model_name": t.model_name, "temperature": t.temperature,
            "max_tokens": t.max_tokens,
            "created_at": t.created_at,
        }

    @staticmethod
    def get_template(template_id):
        try:
            return AIPromptTemplate.objects.get(id=template_id, is_active=True)
        except AIPromptTemplate.DoesNotExist:
            return None

    @staticmethod
    def serialize_template(t):
        return {
            "id": str(t.id), "org_id": t.org_id,
            "created_by": str(t.created_by) if t.created_by else None,
            "name": t.name, "description": t.description, "category": t.category,
            "template_text": t.template_text, "variables": t.variables,
            "is_active": t.is_active, "is_default": t.is_default,
            "model_name": t.model_name, "temperature": t.temperature,
            "max_tokens": t.max_tokens,
            "created_at": t.created_at, "updated_at": t.updated_at,
        }

    @staticmethod
    def update_template(t, data):
        # Snapshot current state BEFORE applying changes
        next_ver = AIPromptTemplateService._next_version_number(t)
        AIPromptTemplateService._snapshot(t, version_number=next_ver)

        editable = ("name", "description", "template_text", "variables",
                    "category", "model_name", "temperature", "max_tokens")
        for field in editable:
            if field in data:
                val = data[field]
                if field in ("name", "template_text") and not str(val).strip():
                    raise ValueError(f"{field} cannot be blank")
                if field == "category":
                    valid = [c[0] for c in AIPromptTemplate.CATEGORY_CHOICES]
                    if val not in valid:
                        raise ValueError(f"category must be one of {valid}")
                setattr(t, field, val)
        t.save()
        return {
            "id": str(t.id), "name": t.name, "category": t.category,
            "template_text": t.template_text,
            "model_name": t.model_name, "temperature": t.temperature,
            "max_tokens": t.max_tokens,
            "updated_at": t.updated_at,
            "version": next_ver,
        }

    @staticmethod
    def delete_template(t):
        t.is_active = False
        t.save(update_fields=["is_active"])

    # ------------------------------------------------------------------ #
    # Versioning
    # ------------------------------------------------------------------ #

    @staticmethod
    def list_versions(template_id):
        t = AIPromptTemplateService.get_template(template_id)
        if not t:
            return None
        versions = list(
            t.versions.values(
                "id", "version_number", "name", "description", "category",
                "template_text", "variables",
                "model_name", "temperature", "max_tokens",
                "created_at",
            )
        )
        return {"template_id": str(t.id), "versions": versions, "count": len(versions)}

    # ------------------------------------------------------------------ #
    # AI Context Builder
    # ------------------------------------------------------------------ #

    @staticmethod
    def build_context(template_id, data: dict) -> dict:
        """
        Renders a prompt template by substituting {{variable}} placeholders
        with values from data (merged lead + campaign + step context).
        Missing variables are left unchanged.
        Returns rendered prompt + template model params.
        """
        t = AIPromptTemplateService.get_template(template_id)
        if not t:
            return None

        def replacer(match):
            key = match.group(1).strip()
            val = data.get(key)
            return str(val) if val is not None else match.group(0)

        rendered = re.sub(r'\{\{(\w+)\}\}', replacer, t.template_text)
        return {
            "rendered_prompt": rendered,
            "template_id": str(t.id),
            "template_name": t.name,
            "model_name": t.model_name,
            "temperature": t.temperature,
            "max_tokens": t.max_tokens,
        }

    @staticmethod
    def rollback_template(template_id, version_number):
        t = AIPromptTemplateService.get_template(template_id)
        if not t:
            return None, "template_not_found"
        try:
            v = t.versions.get(version_number=version_number)
        except AIPromptTemplateVersion.DoesNotExist:
            return None, "version_not_found"

        # Snapshot current state before rolling back
        next_ver = AIPromptTemplateService._next_version_number(t)
        AIPromptTemplateService._snapshot(t, version_number=next_ver)

        # Restore from snapshot
        t.name          = v.name
        t.description   = v.description
        t.category      = v.category
        t.template_text = v.template_text
        t.variables     = v.variables
        t.model_name    = v.model_name
        t.temperature   = v.temperature
        t.max_tokens    = v.max_tokens
        t.save()

        return {
            "id": str(t.id),
            "rolled_back_to_version": version_number,
            "current_version": next_ver,
            "name": t.name, "category": t.category,
            "template_text": t.template_text,
            "model_name": t.model_name, "temperature": t.temperature,
            "max_tokens": t.max_tokens,
            "updated_at": t.updated_at,
        }, None
