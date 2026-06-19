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

_user_actions = {}

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
                salon_id = apt.get("salonId") or (apt.get("salon") or {}).get("_id") or (apt.get("salon") or {}).get("id") or "inconnu"
                apt_id = apt.get("_id") or apt.get("id") or "inconnu"
                lines.append(f"- Rendez-vous le {date_str} au salon '{salon_name}' (ID Salon: {salon_id}) (ID RDV: {apt_id}) (Statut : {status})")
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


@tool
def reschedule_appointment(appointment_id: str, new_date: str, user_id: str) -> str:
    """Reporte ou déplace un rendez-vous existant à une nouvelle date et heure.
    Utilisez cet outil pour répondre à des demandes comme 'déplace le rdv du 19 au 25' ou 'reporte mon rdv'.
    Arguments:
      appointment_id: L'identifiant unique (ID) du rendez-vous à modifier (ID RDV).
      new_date: La nouvelle date et heure souhaitée au format ISO 8601 (ex: '2026-06-25T17:00:00.000Z').
      user_id: L'identifiant du client connecté.
    """
    import re
    if not appointment_id or not re.match(r"^[0-9a-fA-F]{24}$", appointment_id):
        return "Erreur : ID du rendez-vous invalide. Utilisez list_my_appointments pour trouver le bon rdv."
    if not user_id or user_id == "anonymous":
        return "Vous devez être connecté pour modifier un rendez-vous."

    url = f"{settings.nestjs_base_url}/agent/users/{user_id}/appointments/{appointment_id}/reschedule"
    headers = {
        "Content-Type": "application/json",
        "x-api-token": settings.api_shared_token
    }
    payload = {"appointmentDate": new_date}

    try:
        with httpx.Client() as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code in [200, 201]:
                _user_actions[user_id] = "rescheduled"
                return f"Succès : Le rendez-vous a été reporté avec succès au {new_date}."
            else:
                err = resp.text
                try:
                    err_json = resp.json()
                    if isinstance(err_json, dict) and "message" in err_json:
                        err = err_json["message"]
                except:
                    pass
                return f"Échec du report du rendez-vous (code {resp.status_code}) : {err}"
    except Exception as e:
        return f"Erreur lors du report du rendez-vous : {str(e)}"


@tool
def cancel_appointment(appointment_id: str, user_id: str) -> str:
    """Annule un rendez-vous existant du client.
    Utilisez cet outil pour répondre à des demandes comme 'annule mon rendez-vous'.
    Arguments:
      appointment_id: L'identifiant unique (ID) du rendez-vous à annuler (ID RDV).
      user_id: L'identifiant du client connecté.
    """
    import re
    if not appointment_id or not re.match(r"^[0-9a-fA-F]{24}$", appointment_id):
        return "Erreur : ID du rendez-vous invalide. Utilisez list_my_appointments pour trouver le bon rdv."
    if not user_id or user_id == "anonymous":
        return "Vous devez être connecté pour annuler un rendez-vous."

    url = f"{settings.nestjs_base_url}/agent/users/{user_id}/appointments/{appointment_id}/cancel"
    headers = {
        "x-api-token": settings.api_shared_token
    }

    try:
        with httpx.Client() as client:
            resp = client.post(url, headers=headers)
            if resp.status_code in [200, 201]:
                _user_actions[user_id] = "cancelled"
                return "Succès : Le rendez-vous a été annulé avec succès."
            else:
                err = resp.text
                try:
                    err_json = resp.json()
                    if isinstance(err_json, dict) and "message" in err_json:
                        err = err_json["message"]
                except:
                    pass
                return f"Échec de l'annulation du rendez-vous (code {resp.status_code}) : {err}"
    except Exception as e:
        return f"Erreur lors de l'annulation du rendez-vous : {str(e)}"


@tool
def get_available_slots(salon_id: str, date: str, service_id: str = None, duration_minutes: int = 30) -> str:
    """Affiche la liste des créneaux horaires disponibles pour un salon à une date donnée (format YYYY-MM-DD).
    Utilisez cet outil lorsque vous devez proposer des créneaux alternatifs ou vérifier la disponibilité.
    Arguments:
      salon_id: L'identifiant unique (ID) du salon.
      date: La date souhaitée au format YYYY-MM-DD (ex: '2026-06-25').
      service_id: L'identifiant unique de la prestation (optionnel).
      duration_minutes: La durée estimée du service en minutes (par défaut 30, optionnel)."""
    import re
    if not salon_id or not re.match(r"^[0-9a-fA-F]{24}$", salon_id):
        return "Erreur : ID du salon invalide."
    if not date or not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        return "Erreur : Format de date invalide (doit être YYYY-MM-DD)."
        
    url = f"{settings.nestjs_base_url}/salons/{salon_id}/available-slots?date={date}"
    if service_id and re.match(r"^[0-9a-fA-F]{24}$", service_id):
        url += f"&serviceId={service_id}"
    else:
        url += f"&durationMinutes={duration_minutes}"
        
    try:
        with httpx.Client() as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return f"Erreur de récupération des créneaux (code {resp.status_code})."
            data = resp.json()
            available = data.get("available", [])
            if not available:
                return f"Aucun créneau disponible pour le {date}."
            return f"Créneaux disponibles pour le {date} : " + ", ".join(available)
    except Exception as e:
        return f"Erreur de connexion : {str(e)}"


@tool
def search_marketplace_products(query: str) -> str:
    """Recherche des produits en vente et en stock dans tous les salons/boutiques de la plateforme KOUP.
    Utilisez cet outil pour trouver quel salon vend un produit particulier (ex: 'Florame') ou si le produit demandé est disponible sur le réseau.
    Arguments:
      query: Le nom, la marque ou la catégorie du produit à rechercher.
    """
    if not query or len(query.strip()) < 2:
        return "Veuillez fournir un terme de recherche de produit valide d'au moins 2 caractères."
    
    url = f"{settings.nestjs_base_url}/salons/marketplace/search?q={query}"
    headers = {"x-api-token": settings.api_shared_token}
    
    try:
        with httpx.Client() as client:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                return f"Erreur de recherche de produits (code {resp.status_code})."
            data = resp.json()
            if not data or len(data) == 0:
                return f"Aucun produit correspondant à '{query}' n'est disponible en stock actuellement."
            
            lines = []
            for item in data:
                p_name = item.get("name", "Produit")
                p_desc = item.get("description", "")
                p_price = item.get("price", 0)
                p_stock = item.get("stock", 0)
                salon_name = item.get("salonName", "Salon")
                salon_id = item.get("salonId", "inconnu")
                salon_city = item.get("salonCity", "")
                city_part = f" à {salon_city}" if salon_city else ""
                desc_part = f" ({p_desc})" if p_desc else ""
                lines.append(f"- {p_name}{desc_part} : {p_price} FCFA | Stock: {p_stock} | Salon: '{salon_name}' (ID Salon: {salon_id}{city_part})")
            return "\n".join(lines)
    except Exception as e:
        return f"Erreur lors de la recherche de produits : {str(e)}"


@tool
def search_salons_by_service(service_name: str, latitude: float = None, longitude: float = None, date: str = None) -> str:
    """Recherche des salons à proximité proposant une prestation spécifique (ex: 'Coupe classique', 'Tresses').
    Utilisez cet outil pour trouver d'autres salons offrant le service recherché si le salon actuel ne le propose pas.
    Arguments:
      service_name: Le nom de la prestation recherchée.
      latitude: Latitude GPS pour la recherche (optionnel).
      longitude: Longitude GPS pour la recherche (optionnel).
      date: Date au format YYYY-MM-DD (optionnel, par défaut aujourd'hui).
    """
    import datetime
    if not service_name or len(service_name.strip()) < 2:
        return "Veuillez fournir un nom de service valide d'au moins 2 caractères."
        
    lat_val = latitude if latitude is not None else 5.3472
    lng_val = longitude if longitude is not None else -4.0026
    
    if not date:
        date = datetime.date.today().isoformat()
        
    url = f"{settings.nestjs_base_url}/salons/matchmaking?lat={lat_val}&lng={lng_val}&date={date}&serviceName={service_name}&skipAvailability=true"
    headers = {"x-api-token": settings.api_shared_token}
    
    try:
        with httpx.Client() as client:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                return f"Erreur lors de la recherche de salons (code {resp.status_code})."
            data = resp.json()
            matches = data.get("matches", [])
            if not matches:
                return f"Aucun salon à proximité ne propose la prestation '{service_name}' pour le moment."
                
            lines = []
            for item in matches:
                salon = item.get("salon", {})
                salon_id = salon.get("_id") or salon.get("id") or "inconnu"
                salon_name = salon.get("name") or salon.get("salonName") or "Salon"
                salon_address = salon.get("address", "Adresse non spécifiée")
                dist = item.get("distanceInMeters")
                dist_str = f" ({round(dist/1000, 1)} km)" if dist is not None else ""
                
                # Prestation correspondante
                svc = item.get("service", {})
                svc_name = svc.get("name", service_name)
                svc_price = svc.get("price", 0)
                svc_duration = svc.get("minDurationUnits", svc.get("durationMinutes", 30))
                
                lines.append(f"- ID: {salon_id} | {salon_name} : Situé à {salon_address}{dist_str} | Offre : '{svc_name}' à {svc_price} FCFA ({svc_duration} min)")
            return "\n".join(lines)
    except Exception as e:
        return f"Erreur lors de la recherche de salons par service : {str(e)}"


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

    async def chat(self, messages: list, user_id: str, latitude: float = None, longitude: float = None, client_context: str = None) -> dict:
        if self.client is None:
            return {
                "model": settings.ollama_model,
                "content": "Désolée, le moteur d'agent intelligent (DeerFlow) n'est pas disponible pour le moment.",
                "done": True
            }

        _user_actions[user_id] = None
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
            "1. Sois extrêmement chaleureuse, accueillante, naturelle, de bonne humeur, et concise (1 à 3 phrases courtes maximum par réponse). "
            "2. N'affiche JAMAIS d'identifiants techniques (IDs de 24 caractères comme salon_id, service_id, ou appointment_id) dans le texte principal destiné à l'utilisateur. Utilise des expressions simples, claires, et parfaitement compréhensibles par tous. "
            "3. Rends tes réponses vivantes et dynamiques en utilisant généreusement des émoticônes/émojis et des puces scintillantes (ex: ✨, 💇, 📅, 💈, 🌟, 💫) pour marquer les étapes ou les choix. "
            "4. Si tu dois présenter des choix (salons, prestations/services, rendez-vous, produits ou créneaux) : "
            "   - Tu dois TOUJOURS numéroter ces choix dans le texte principal destiné à l'utilisateur (ex: '1. Moya delux, 2. Salon Alliance...') pour que les utilisateurs vocaux puissent facilement énoncer leur sélection ('Je choisis le 1', 'Le premier'). "
            "   - Place-les ensuite TOUJOURS à la fin de ta réponse sous l'un des formats bruts stricts suivants pour que l'application puisse les intercepter, les animer et les afficher sous forme de jolies cartes interactives sans que l'utilisateur ne voie les IDs :\n"
            "     * Pour les salons : `- ID: <id_salon> | <Nom du Salon> : Situé à <Adresse>`\n"
            "     * Pour les prestations : `- ID: <id_prestation> | <Nom de la Prestation> : <Prix> FCFA | <Durée> min`\n"
            "     * Pour les rendez-vous : `- Rendez-vous le <Date ISO ou claire> au salon '<Nom du Salon>' (ID Salon: <id_salon>) (ID RDV: <id_rdv>) (Statut : <Statut>)`\n"
            "   Ne cite JAMAIS ces identifiants (IDs) en dehors de ces formats de liste brute en fin de message.\n"
            "5. Règles pour le report (reschedule) d'un rendez-vous :\n"
            "   - Tu dois TOUJOURS respecter la politique du salon et la disponibilité des places.\n"
            "   - Si tu essaies de reporter et que l'outil te signale que le créneau est indisponible (ex: 'Créneau indisponible'), appelle immédiatement l'outil `get_available_slots` pour cette date (avec le salon_id et éventuellement le service_id de la prestation si tu le connais) pour voir les autres créneaux de libre, et propose activement ces alternatives au client.\n"
            "   - Si tu essaies de reporter et que l'outil te signale que le délai de report est dépassé, informe poliment le client que la politique du salon ne permet plus de modifier ce rendez-vous à ce stade. Propose-lui alors de choisir entre maintenir son rendez-vous à la date actuelle ou bien de l'annuler complètement.\n"
            "6. INTERDICTION ABSOLUE D'INVENTER : Tu ne dois sous aucun prétexte inventer, halluciner, imaginer ou générer des salons, prestations, créneaux horaires ou informations fictifs (comme 'Hair-Care SF', 'Locks & Co', etc.) qui ne sont pas explicitement retournés par tes outils. Base-toi UNIQUEMENT et STRICTEMENT sur les données réelles renvoyées par les outils (comme list_salons ou get_available_slots). S'il n'y a qu'un seul salon à proximité dans la base de données, affiche uniquement celui-ci. Si aucun salon n'est retourné par l'outil, réponds poliment que tu n'as trouvé aucun salon disponible à proximité.\n"
            "7. FIN DES OPTIONS APRÈS SÉLECTION : Dès que l'utilisateur a sélectionné et validé un choix (par exemple, s'il a cliqué sur 'Valider le choix' d'un salon ou a écrit 'Je choisis le salon ...'), ce choix est considéré comme définitivement acquis. Tu ne dois plus JAMAIS ré-afficher cette option ou ce salon sous forme de liste brute (`- ID: ...`) à la fin de tes réponses suivantes. Pose simplement la question d'après (par exemple, demander la date ou la prestation souhaitée) uniquement par du texte simple.\n"
            "8. RECHERCHE AUTONOME DES CRÉNEAUX : Si l'utilisateur a choisi un salon pour voir les créneaux disponibles (ou si l'historique montre qu'il cherche des créneaux libres), sois autonome et proactive. N'attends pas qu'il te donne une date ! Utilise directement l'outil `get_available_slots` pour la date d'aujourd'hui (fournie dans le contexte) ou celle de demain. Propose-lui ensuite directement les horaires de créneaux trouvés afin qu'il n'ait pas à deviner ou à saisir la date lui-même.\n"
            "9. UTILISATION ACTIVE DU PROFIL ET DES HABITUDES : Analyse le profil beauté (ex: type de cheveux 'Locks', type de peau, styles) et les habitudes (panier moyen, produit préféré comme 'Florame', prestation phare) fournis dans le contexte. Si l'utilisateur demande des conseils de style, de soins ou des suggestions de prestations, propose-lui DIRECTEMENT des solutions adaptées à son profil (ex: soins pour locks) sans lui poser de questions sur ses caractéristiques physiques, car tu les as déjà dans son profil !\n"
            "10. PROACTIVITÉ EN CAS D'ABSENCE DE PRODUIT OU SERVICE : Si l'utilisateur demande une prestation ou un produit spécifique, tu devez d'abord interroger `get_salon_details` pour le salon concerné. Si le produit ou la prestation demandée (comme son produit favori 'Florame') n'est pas disponible dans ce salon :\n"
            "   - Propose immédiatement une alternative équivalente en stock ou disponible dans ce même salon en te basant sur son profil (ex: un autre shampoing ou soin adapté disponible dans le salon).\n"
            "   - ET appelle automatiquement l'outil `search_marketplace_products` (pour les produits) ou `search_salons_by_service` (pour les services) pour rechercher d'autres salons à proximité disposant du produit ou de la prestation d'origine, puis propose-lui ces salons sous forme de liste brute (`- ID: ...` ou liste de produits) pour qu'il puisse les choisir.\n"
            "11. CONFIRMATION EXPLICITE AVANT RÉSERVATION OU ACTION : Ne réserve, ne reporte et n'annule JAMAIS un rendez-vous (ne lance pas book_appointment, reschedule_appointment ou cancel_appointment) de manière automatique ou à la première sélection de l'utilisateur. Tu dois TOUJOURS poser la question de confirmation d'abord (ex: 'Souhaitez-vous que je réserve cette prestation pour vous ?' ou 'Voulez-vous confirmer ce report ?') et attendre l'accord explicite du client (ex: 'Oui', 'Je confirme', 'Vas-y') avant d'exécuter l'outil correspondant.\n"
            "12. GESTION DU CHOIX NUMÉRIQUE : Si l'utilisateur énonce un numéro de la liste (ex: 'Je choisis le 1', 'Le premier'), retrouve l'élément correspondant dans la liste numérotée que tu as présentée dans ton précédent message et utilise son ID technique associé pour appeler l'outil ou continuer l'action."
        )

        # Injecter le contexte de localisation, d'identité de l'utilisateur, de la date courante et du profil beauté/habitudes
        import datetime
        now = datetime.datetime.now()
        current_date_str = now.strftime("%Y-%m-%d")
        current_time_str = now.strftime("%H:%M")
        day_of_week_fr = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"][now.weekday()]

        context_parts = [
            f"Utilisateur connecté : user_id={user_id}",
            f"Date actuelle : {current_date_str} ({day_of_week_fr})",
            f"Heure actuelle : {current_time_str}"
        ]
        if latitude is not None and longitude is not None:
            context_parts.append(f"Localisation GPS : latitude={latitude}, longitude={longitude}")
        if client_context:
            context_parts.append(f"Profil Beauté & Habitudes du client connecté :\n{client_context}")
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

            action = _user_actions.pop(user_id, None)
            return {
                "model": settings.ollama_model,
                "content": response_text,
                "done": True,
                "actionPerformed": action
            }
        except Exception as e:
            logger.error("Erreur lors de l'appel à l'agent Kora via DeerFlowClient.chat: %s", str(e), exc_info=True)
            return {
                "model": settings.ollama_model,
                "content": f"Désolée, une erreur interne s'est produite lors de la génération. ({str(e)})",
                "done": True
            }


