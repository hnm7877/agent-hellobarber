import httpx
try:
    from langchain_ollama import ChatOllama
except ImportError:
    try:
        from langchain_community.chat_models import ChatOllama
    except ImportError:
        class ChatOllama:
            def __init__(self, **kwargs):
                pass

try:
    from langchain_core.runnables import RunnableConfig
    from langchain_core.tools import tool
except ImportError:
    def tool(func):
        return func
    class RunnableConfig(dict):
        pass

try:
    from deerflow.agents import create_deerflow_agent, RuntimeFeatures
except ImportError:
    def create_deerflow_agent(*args, **kwargs):
        class DummyAgent:
            async def ainvoke(self, *args, **kwargs):
                return {"messages": [{"role": "assistant", "content": "DeerFlow Harness non disponible dans cet environnement."}]}
        return DummyAgent()
    class RuntimeFeatures:
        def __init__(self, **kwargs):
            pass

from app.settings import get_settings

settings = get_settings()

@tool
def list_salons(config: RunnableConfig) -> str:
    """Affiche la liste de tous les salons de coiffure et de beauté disponibles sur la plateforme KOUP.
    Utilisez cet outil pour répondre à des questions comme 'quels sont les salons disponibles ?' ou 'suggère-moi un salon coiffure'."""
    configurable = config.get("configurable", {})
    lat = configurable.get("latitude")
    lng = configurable.get("longitude")
    
    if lat is not None and lng is not None:
        url = f"{settings.nestjs_base_url}/salons/nearby?lat={lat}&lng={lng}&maxDistance=100000"
    else:
        url = f"{settings.nestjs_base_url}/agent/salons"
        
    headers = {"x-api-token": settings.api_shared_token}
    
    try:
        with httpx.Client() as client:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                return f"Erreur de récupération des salons (code {resp.status_code})."
            data = resp.json()
            if not data or len(data) == 0:
                return "Aucun salon n'est répertorié sur la plateforme pour le moment."
            
            lines = []
            for salon in data:
                salon_id = salon.get("_id") or salon.get("id") or "ID inconnu"
                name = salon.get("salonName") or salon.get("name") or "Salon sans nom"
                address = salon.get("address", "Adresse non spécifiée")
                rating = salon.get("rating", "Pas de note")
                specialty_list = salon.get("specialtyCodes") or salon.get("specialties") or []
                if isinstance(specialty_list, str):
                    specialties = specialty_list
                else:
                    specialties = ", ".join(str(s) for s in specialty_list)
                lines.append(f"- ID: {salon_id} | {name} : Situé à {address} | Note : {rating}/5 | Catégories/Spécialités générales : {specialties} (Note: Ce ne sont pas des prestations réservables directement. Pour obtenir la liste réelle des prestations de ce salon et leurs tarifs, vous devez impérativement appeler get_salon_services).")
            return "\n".join(lines)
    except Exception as e:
        return f"Erreur de connexion au service d'administration : {str(e)}"


@tool
def list_my_appointments(config: RunnableConfig) -> str:
    """Affiche la liste des rendez-vous (confirmés, passés, futurs) du client actuellement connecté.
    Utilisez cet outil pour répondre à des questions comme 'quels sont mes rendez-vous ?' ou 'quand est mon prochain rendez-vous ?'."""
    user_id = config.get("configurable", {}).get("user_id")
    if not user_id or user_id == "anonymous":
        return "Vous n'êtes pas connecté. Veuillez vous connecter pour voir vos rendez-vous."
    
    url = f"{settings.nestjs_base_url}/agent/users/{user_id}/appointments"
    headers = {"x-api-token": settings.api_shared_token}
    
    try:
        with httpx.Client() as client:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                return f"Erreur de récupération des rendez-vous (code {resp.status_code})."
            data = resp.json()
            if not data or len(data) == 0:
                return "Vous n'avez aucun rendez-vous actuellement."
            
            # Format nicely
            lines = []
            for apt in data:
                date_str = apt.get("appointmentDate", "inconnue")
                status = apt.get("status", "inconnu")
                salon_name = apt.get("salonName") or apt.get("salon", {}).get("salonName") or "un salon KOUP"
                lines.append(f"- Rendez-vous le {date_str} au salon '{salon_name}' (Statut : {status})")
            return "\n".join(lines)
    except Exception as e:
        return f"Erreur de connexion au service d'administration : {str(e)}"


@tool
def get_salon_services(salon_id: str) -> str:
    """Affiche la liste des prestations de coiffure ou beauté disponibles (ID, nom, prix, durée) pour un salon spécifique.
    Utilisez cet outil lorsqu'un utilisateur demande 'quelles sont les prestations de ce salon ?' ou exprime l'intention de réserver pour voir les services disponibles."""
    import re
    if not salon_id or not re.match(r"^[0-9a-fA-F]{24}$", salon_id):
        return "Erreur : ID du salon invalide (doit être un identifiant unique de 24 caractères hexadécimaux). Utilisez d'abord list_salons pour trouver le bon ID."
        
    url = f"{settings.nestjs_base_url}/salons/{salon_id}/detail"
    
    try:
        with httpx.Client() as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return f"Erreur de récupération des détails du salon (code {resp.status_code})."
            data = resp.json()
            services = data.get("services", [])
            if not services or len(services) == 0:
                return "Aucune prestation n'est disponible dans ce salon actuellement."
            
            lines = []
            for svc in services:
                svc_id = svc.get("_id")
                name = svc.get("name", "Prestation sans nom")
                price = svc.get("price", 0)
                duration = svc.get("minDurationUnits", svc.get("duration", 30))
                lines.append(f"- ID: {svc_id} | {name} : Tarif : {price} FCFA | Durée : {duration} min")
            return "\n".join(lines)
    except Exception as e:
        return f"Erreur lors de la récupération des prestations : {str(e)}"


@tool
def book_appointment(salon_id: str, service_id: str, appointment_date: str, config: RunnableConfig) -> str:
    """Réserve un rendez-vous (crée une réservation) pour le client actuellement connecté dans un salon pour une prestation à une date donnée.
    Arguments:
      salon_id: L'identifiant unique (ID) du salon.
      service_id: L'identifiant unique (ID) de la prestation.
      appointment_date: Date et heure du rendez-vous au format ISO 8601 (ex: '2026-06-18T17:00:00.000Z').
    """
    import re
    if not salon_id or not re.match(r"^[0-9a-fA-F]{24}$", salon_id):
        return "Erreur : ID du salon invalide (doit être un identifiant unique de 24 caractères hexadécimaux). Utilisez d'abord list_salons pour trouver le bon ID."
    if not service_id or not re.match(r"^[0-9a-fA-F]{24}$", service_id):
        return "Erreur : ID de la prestation (service_id) invalide (doit être un identifiant unique de 24 caractères hexadécimaux). Utilisez d'abord get_salon_services avec l'ID du salon pour obtenir la liste des prestations réelles et leurs identifiants."
        
    user_id = config.get("configurable", {}).get("user_id")
    if not user_id or user_id == "anonymous":
        return "Vous devez être connecté pour réserver. Veuillez vous connecter dans l'application."
        
    url = f"{settings.nestjs_base_url}/agent/users/{user_id}/appointments"
    headers = {
        "Content-Type": "application/json",
        "x-api-token": settings.api_shared_token
    }
    payload = {
        "salonId": salon_id,
        "serviceId": service_id,
        "appointmentDate": appointment_date
    }
    
    try:
        with httpx.Client() as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code in [200, 201]:
                data = resp.json()
                apt_id = data.get("_id")
                date_val = data.get("appointmentDate", appointment_date)
                price = data.get("billingFinalPrice", 0)
                client_name = data.get("clientName", "Client")
                return f"Succès : Rendez-vous réservé avec succès pour {client_name} le {date_val}. Prix final : {price} FCFA. ID Réservation : {apt_id}."
            else:
                err_detail = resp.text
                try:
                    err_json = resp.json()
                    if isinstance(err_json, dict) and "message" in err_json:
                        err_detail = err_json["message"]
                except:
                    pass
                return f"Échec de la réservation (Code {resp.status_code}) : {err_detail}"
    except Exception as e:
        return f"Erreur lors de la réservation : {str(e)}"


class KoraAgentService:
    def __init__(self):
        # Configure model
        self.model = ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            timeout=settings.ollama_timeout,
        )
        
        # System prompt
        self.system_prompt = (
            "Tu es Kora ✨, l'assistante beauté intelligente de KOUP.\n"
            "Tu es un esprit de beauté africain premium, bienveillante, experte et raffinée.\n"
            "Réponds toujours en français.\n"
            "Sois concise, chaleureuse, utile et professionnelle.\n\n"
            "CADRE STRICT D'INTERACTION ET RÈGLES DE CONTEXTE :\n"
            "1. Rôle & Domaine Exclusif : Tu es une conseillère spécialisée uniquement en coiffure (afro, tresses, locks, etc.), barbering, onglerie, maquillage, soins de la peau, esthétique et bien-être. Tu ne dois JAMAIS répondre à des questions hors sujet. Si on te pose une question hors contexte, refuse poliment et réoriente immédiatement la discussion vers la beauté ou les prestations de salon.\n"
            "2. Continuité & Fluidité : L'échange est continu. Utilise l'historique de la discussion pour comprendre les préoccupations passées de l'utilisateur et construire une réponse fluide sans te répéter ou redemander des détails déjà fournis.\n"
            "3. Pas de détails techniques ni d'identifiants (RÈGLE ABSOLUE) : Ne montre JAMAIS d'identifiants techniques (comme les MongoDB ObjectIDs du type '6a21a0aad1efe8aa1c6a2e41', etc.) ou de noms de fonctions/outils internes à l'utilisateur. Toutes ces informations techniques doivent être utilisées en arrière-plan. Dans tes réponses textuelles, utilise exclusivement les noms compréhensibles par un client (ex: 'Barber La Main d'or', 'Prestation de tresses').\n"
            "4. Utilise uniquement les données réelles (Pas d'invention) : Ne fabrique pas de salons, de tarifs, de prestations ou d'horaires. Attention : les 'spécialités' ou 'catégories' renvoyées par la liste des salons ne sont que des compétences générales et ne correspondent pas à des prestations réservables directement. Pour parler des prestations d'un salon ou tenter une réservation, tu dois impérativement appeler l'outil des prestations de ce salon pour obtenir sa liste réelle de prestations configurées (ex: 'Coupe classique', 'Métal detox'). Si un service demandé (ex: 'braids') ne figure pas dans cette liste réelle, explique gentiment au client que le salon ne le propose pas et liste-lui les prestations réellement disponibles dans ce salon.\n"
            "5. Processus de Réservation : Quand l'utilisateur souhaite prendre un rendez-vous (ex: 'réserve pour moi', 'je veux prendre RDV'), tu dois :\n"
            "   a. Identifier le salon choisi (utilise l'outil de liste des salons si nécessaire).\n"
            "   b. Lister et vérifier les prestations de ce salon (utilise l'outil des prestations du salon) pour trouver la prestation correspondante.\n"
            "   c. Confirmer le jour et l'heure souhaités par l'utilisateur.\n"
            "   d. Exécuter la réservation (utilise l'outil de réservation de rendez-vous) avec la date formatée en ISO 8601 (ex: '2026-06-18T17:00:00.000Z'). Ne passe jamais d'ID vide ou fictif.\n"
            "   e. Confirmer le succès de la réservation au client avec le prix final, la date et l'heure de manière naturelle et chaleureuse, sans mentionner d'ID."
        )
        
        # Tools list
        self.tools = [list_salons, list_my_appointments, get_salon_services, book_appointment]
        
        # Compile DeerFlow agent
        self.agent = create_deerflow_agent(
            model=self.model,
            system_prompt=self.system_prompt,
            tools=self.tools,
            features=RuntimeFeatures(subagent=False, memory=True),
            name="kora-beauty-agent",
        )

    async def chat(self, messages: list, user_id: str, latitude: float = None, longitude: float = None) -> dict:
        config = {
            "configurable": {
                "user_id": user_id,
                "thread_id": f"kora-session-{user_id}",
                "latitude": latitude,
                "longitude": longitude,
            }
        }
        
        # Format messages for langchain (role: user -> HumanMessage, assistant -> AIMessage)
        formatted_messages = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")
            if role == "user":
                formatted_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                formatted_messages.append({"role": "assistant", "content": content})
                
        # Invoke agent graph
        result = await self.agent.ainvoke(
            {"messages": formatted_messages},
            config=config
        )
        
        # Extract response message
        # result["messages"] contains the conversation state including tool calls and the final agent response
        final_message = ""
        for m in reversed(result.get("messages", [])):
            if hasattr(m, "content") and m.content and m.type == "ai":
                final_message = m.content
                break
            elif isinstance(m, dict) and m.get("role") == "assistant" and m.get("content"):
                final_message = m.get("content")
                break
                
        return {
            "model": settings.ollama_model,
            "content": final_message or "Désolée, je n'ai pas pu formuler de réponse.",
            "done": True
        }
