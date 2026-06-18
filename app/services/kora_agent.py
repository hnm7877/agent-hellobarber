import httpx
import logging

import os
from dotenv import load_dotenv

# Charger le fichier .env dans les variables d'environnement OS
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
load_dotenv(dotenv_path=env_path)

from langchain_core.tools import tool

try:
    from deerflow.config.app_config import reload_app_config  # type: ignore
    from deerflow.client import DeerFlowClient  # type: ignore
except ImportError:
    reload_app_config = None
    DeerFlowClient = None


from app.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

@tool
def list_salons(latitude: float = None, longitude: float = None) -> str:
    """Affiche la liste de tous les salons de coiffure et de beauté disponibles sur la plateforme KOUP.
    Utilisez cet outil pour répondre à des questions comme 'quels sont les salons disponibles ?' ou 'suggère-moi un salon coiffure'.
    Arguments:
      latitude: Latitude GPS du client (optionnel, pour trouver les salons à proximité).
      longitude: Longitude GPS du client (optionnel, pour trouver les salons à proximité)."""
    if latitude is not None and longitude is not None:
        url = f"{settings.nestjs_base_url}/salons/nearby?lat={latitude}&lng={longitude}&maxDistance=100000"
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
                lines.append(f"- ID: {salon_id} | {name} : Situé à {address} | Note : {rating}/5 | Catégories/Spécialités générales : {specialties} (Note: Ce ne sont pas des prestations réservables directement. Pour obtenir les détails du salon, ses horaires, ses prestations réelles et ses produits, vous devez impérativement appeler get_salon_details).")
            return "\n".join(lines)
    except Exception as e:
        return f"Erreur de connexion au service d'administration : {str(e)}"


@tool
def list_my_appointments(user_id: str) -> str:
    """Affiche la liste des rendez-vous (confirmés, passés, futurs) du client actuellement connecté.
    Utilisez cet outil pour répondre à des questions comme 'quels sont mes rendez-vous ?' ou 'quand est mon prochain rendez-vous ?'.
    Arguments:
      user_id: L'identifiant de l'utilisateur connecté."""
    import re
    if not user_id or user_id == "anonymous" or not re.match(r"^[0-9a-fA-F]{24}$", user_id):
        return "Vous devez être connecté avec un compte valide pour voir vos rendez-vous."
    
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
def get_salon_details(salon_id: str) -> str:
    """Affiche les détails complets d'un salon (description, adresse, téléphone, horaires d'ouverture, prestations/services disponibles, collaborateurs/staff et produits vendus).
    Utilisez cet outil lorsqu'un utilisateur demande des informations détaillées sur un salon, ses prestations, ses tarifs, son adresse, ses horaires, son staff ou ses produits."""
    import re
    if not salon_id or not re.match(r"^[0-9a-fA-F]{24}$", salon_id):
        return "Erreur : ID du salon invalide (doit être un identifiant unique de 24 caractères hexadécimaux). Utilisez d'abord list_salons pour trouver le bon ID."
        
    detail_url = f"{settings.nestjs_base_url}/salons/{salon_id}/detail"
    products_url = f"{settings.nestjs_base_url}/salons/{salon_id}/products"
    
    try:
        with httpx.Client() as client:
            # 1. Fetch details, services, reviews, staff
            resp = client.get(detail_url)
            if resp.status_code != 200:
                return f"Erreur de récupération des détails du salon (code {resp.status_code})."
            data = resp.json()
            
            # 2. Fetch products
            products = []
            try:
                prod_resp = client.get(products_url)
                if prod_resp.status_code == 200:
                    products = prod_resp.json()
            except Exception:
                pass
            
            salon = data.get("salon") or {}
            services = data.get("services", [])
            staff = data.get("staff", [])
            
            name = salon.get("name") or salon.get("salonName") or "Salon"
            description = salon.get("description", "Aucune description.")
            address = salon.get("address", "Adresse non spécifiée.")
            phone = data.get("salonPhone") or salon.get("phone") or "Non spécifié."
            
            # Format opening hours
            DAYS_FR = {1: "Lundi", 2: "Mardi", 3: "Mercredi", 4: "Jeudi", 5: "Vendredi", 6: "Samedi", 7: "Dimanche"}
            hours_list = salon.get("weeklyOpeningHours", [])
            hours_str = ""
            if hours_list:
                for h in hours_list:
                    day_name = DAYS_FR.get(h.get("weekday"), f"Jour {h.get('weekday')}")
                    if h.get("isOpen"):
                        periods = ", ".join([f"{p.get('start')} à {p.get('end')}" for p in h.get("periods", [])])
                        hours_str += f"- {day_name} : {periods}\n"
                    else:
                        hours_str += f"- {day_name} : Fermé\n"
            else:
                hours_str = "Non renseignés.\n"
                
            # Format services
            services_str = ""
            if services:
                for s in services:
                    svc_id = s.get("_id") or s.get("id")
                    s_name = s.get("name", "Prestation")
                    price = s.get("price", 0)
                    duration = s.get("minDurationUnits", s.get("duration", 30))
                    services_str += f"- ID: {svc_id} | {s_name} : {price} FCFA | {duration} min\n"
            else:
                services_str = "Aucune prestation disponible.\n"
                
            # Format products
            products_str = ""
            if products:
                for p in products:
                    p_name = p.get("name", "Produit")
                    p_desc = p.get("description", "")
                    p_price = p.get("price", 0)
                    p_stock = p.get("stock", 0)
                    desc_part = f" ({p_desc})" if p_desc else ""
                    products_str += f"- {p_name}{desc_part} : {p_price} FCFA | Stock: {p_stock}\n"
            else:
                products_str = "Aucun produit en vente.\n"
                
            # Format staff
            staff_str = ""
            if staff:
                for st in staff:
                    st_name = st.get("name", "Collaborateur")
                    st_specialties = ", ".join(st.get("specialties", []))
                    spec_part = f" (Spécialités: {st_specialties})" if st_specialties else ""
                    staff_str += f"- {st_name}{spec_part}\n"
            else:
                staff_str = "Aucun collaborateur renseigné.\n"
                
            # Combine everything
            result = (
                f"Détails du salon : {name}\n"
                f"Description : {description}\n"
                f"Adresse : {address}\n"
                f"Téléphone : {phone}\n\n"
                f"Horaires d'ouverture :\n{hours_str}\n"
                f"Collaborateurs disponibles :\n{staff_str}\n"
                f"Prestations de coiffure / beauté disponibles (utilisez ces IDs réels pour réserver) :\n{services_str}\n"
                f"Produits disponibles :\n{products_str}"
            )
            return result
    except Exception as e:
        return f"Erreur lors de la récupération des détails du salon : {str(e)}"


@tool
def book_appointment(salon_id: str, service_id: str, appointment_date: str, user_id: str) -> str:
    """Réserve un rendez-vous (crée une réservation) pour le client actuellement connecté dans un salon pour une prestation à une date donnée.
    Arguments:
      salon_id: L'identifiant unique (ID) du salon.
      service_id: L'identifiant unique (ID) de la prestation.
      appointment_date: Date et heure du rendez-vous au format ISO 8601 (ex: '2026-06-18T17:00:00.000Z').
      user_id: L'identifiant de l'utilisateur connecté.
    """
    import re
    if not salon_id or not re.match(r"^[0-9a-fA-F]{24}$", salon_id):
        return "Erreur : ID du salon invalide (doit être un identifiant unique de 24 caractères hexadécimaux). Utilisez d'abord list_salons pour trouver le bon ID."
    if not service_id or not re.match(r"^[0-9a-fA-F]{24}$", service_id):
        return "Erreur : ID de la prestation (service_id) invalide (doit être un identifiant unique de 24 caractères hexadécimaux). Utilisez d'abord get_salon_details avec l'ID du salon pour obtenir la liste des prestations réelles et leurs identifiants."
        
    if not user_id or user_id == "anonymous" or not re.match(r"^[0-9a-fA-F]{24}$", user_id):
        return "Vous devez être connecté avec un compte valide pour réserver. Veuillez vous connecter dans l'application."
        
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
        if reload_app_config is None or DeerFlowClient is None:
            self.client = None
            logger.error("DeerFlow Harness non disponible dans cet environnement (deerflow-kernel non installé).")
            return

        config_path = os.getenv("DEER_FLOW_CONFIG_PATH") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "config.yaml"))
        if os.path.exists(config_path):
            try:
                reload_app_config(config_path=config_path)
                logger.info(f"DeerFlow configuration loaded from {config_path}")
            except Exception as e:
                logger.error(f"Failed to load DeerFlow configuration from {config_path}: {str(e)}")
        else:
            logger.warning(f"DeerFlow config file not found at {config_path}")

        try:
            self.client = DeerFlowClient()
            logger.info("KoraAgentService initialized with DeerFlowClient.")
        except Exception as e:
            self.client = None
            logger.error(f"Failed to initialize DeerFlowClient: {str(e)}")

    async def chat(self, messages: list, user_id: str, latitude: float = None, longitude: float = None) -> dict:
        if self.client is None:
            return {
                "model": settings.ollama_model,
                "content": "Désolée, le moteur d'agent intelligent (DeerFlow) n'est pas disponible pour le moment.",
                "done": True
            }

        # Extraire le dernier message de l'utilisateur
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break

        if not user_message:
            user_message = "Bonjour"

        # Directives de sécurité et formatage pour échange vocal/assistant
        system_rules = (
            "Tu es Kora, l'assistante beauté IA de la plateforme KOUP. "
            "RÈGLES IMPORTANTES DE SÉCURITÉ ET DE COMPORTEMENT : "
            "1. Sois chaleureuse, naturelle et très concise (1 à 3 phrases courtes maximum par réponse) pour être facilement lue par synthèse vocale. "
            "2. N'affiche JAMAIS de détails techniques sur le fonctionnement interne de l'application, l'API, les bases de données ou l'architecture (réponds poliment que tu es là pour les rendez-vous et redirige vers le support en cas de souci technique). "
            "3. Ne divulgue JAMAIS d'informations (noms, téléphones, rendez-vous) d'autres clients ou utilisateurs pour des raisons de confidentialité et sécurité strictes."
        )

        # Injecter le contexte de localisation et d'identité de l'utilisateur
        context_parts = [f"Utilisateur connecté : user_id={user_id}"]
        if latitude is not None and longitude is not None:
            context_parts.append(f"Localisation GPS : latitude={latitude}, longitude={longitude}")
        context_msg = " | ".join(context_parts)
        
        full_message = f"[Directives: {system_rules}]\n[Contexte: {context_msg}]\n\n{user_message}"
        thread_id = f"kora-session-{user_id}"

        try:
            import asyncio
            response_text = await asyncio.to_thread(
                self.client.chat,
                full_message,
                thread_id=thread_id
            )

            return {
                "model": settings.ollama_model,
                "content": response_text,
                "done": True
            }
        except Exception as e:
            logger.error("Erreur lors de l'appel à l'agent Kora via DeerFlowClient.chat: %s", str(e), exc_info=True)
            return {
                "model": settings.ollama_model,
                "content": f"Désolée, une erreur interne s'est produite lors de la génération. ({str(e)})",
                "done": True
            }


