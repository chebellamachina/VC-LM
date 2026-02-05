import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import calendar
import os
from database import (
    init_database, get_users, add_user, delete_user, get_providers, add_provider,
    get_provider_by_name, create_payment_request, get_payment_requests,
    get_payment_request, update_payment_status, approve_cfo, reject_cfo,
    get_stats, UPLOADS_DIR
)

# Page configuration
st.set_page_config(
    page_title="Sistema de Solicitud de Pagos",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============== SIMPLE AUTHENTICATION ==============
# Password stored in Streamlit secrets (or fallback for local dev)
APP_PASSWORD = st.secrets.get("app_password", "vcpagos2024")

def check_password():
    """Returns True if the user has entered the correct password."""

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    # Show login form
    st.title("🔐 Sistema de Solicitud de Pagos")
    st.markdown("---")

    with st.form("login_form"):
        password = st.text_input("Contraseña", type="password", placeholder="Ingrese la contraseña")
        submitted = st.form_submit_button("Ingresar", use_container_width=True)

        if submitted:
            if password == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("❌ Contraseña incorrecta")

    return False

# Check authentication before showing the app
if not check_password():
    st.stop()

# Initialize database
init_database()

# Custom CSS
st.markdown("""
<style>
    .stAlert {
        margin-top: 1rem;
    }
    .status-pendiente {
        background-color: #fff3cd;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        color: #856404;
    }
    .status-en_proceso {
        background-color: #cce5ff;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        color: #004085;
    }
    .status-completado {
        background-color: #d4edda;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        color: #155724;
    }
    .status-rechazado {
        background-color: #f8d7da;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        color: #721c24;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        text-align: center;
    }
</style>
""", unsafe_allow_html=True)


def save_uploaded_file(uploaded_file, prefix: str) -> str:
    """Save an uploaded file and return its path."""
    if uploaded_file is None:
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}_{uploaded_file.name}"
    filepath = os.path.join(UPLOADS_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(uploaded_file.getbuffer())

    return filepath


def format_currency(amount: float) -> str:
    """Format amount as currency."""
    return f"${amount:,.2f}"


def get_status_badge(status: str) -> str:
    """Return HTML badge for status."""
    status_labels = {
        'pendiente': '⏳ Pendiente Pao',
        'aprobado_cfo': '✅ Aprobado Pao',
        'en_proceso': '🔄 En Proceso (Tesorería)',
        'completado': '💚 Completado',
        'rechazado': '❌ Rechazado'
    }
    return status_labels.get(status, status)


# Sidebar navigation
st.sidebar.title("💰 Sistema de Pagos")

# Logout button
if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
    st.session_state.authenticated = False
    st.rerun()

st.sidebar.markdown("---")

view = st.sidebar.radio(
    "Seleccionar Vista",
    ["🏭 Producción - Solicitar Pago", "📊 Admin - Gestionar Pagos", "📅 Calendario de Pagos", "💹 Cashflow Proyectado", "⚙️ Configuración"]
)

st.sidebar.markdown("---")

# Show stats in sidebar
stats = get_stats()
st.sidebar.subheader("📈 Resumen")

pendiente = stats.get('pendiente', {'count': 0, 'total': 0})
en_proceso = stats.get('en_proceso', {'count': 0, 'total': 0})
completado = stats.get('completado', {'count': 0, 'total': 0})

st.sidebar.metric("Pendientes", f"{pendiente['count']} ({format_currency(pendiente['total'])})")
st.sidebar.metric("En Proceso", f"{en_proceso['count']} ({format_currency(en_proceso['total'])})")
st.sidebar.metric("Completados", f"{completado['count']} ({format_currency(completado['total'])})")


# ============== PRODUCTION VIEW ==============
if view == "🏭 Producción - Solicitar Pago":
    st.title("🏭 Solicitar Pago")
    st.markdown("Complete el formulario para solicitar un pago al equipo de Administración y Finanzas.")

    # User selection
    users = get_users(team="produccion")
    user_names = [u['name'] for u in users]

    if not user_names:
        st.warning("No hay usuarios de producción configurados. Vaya a Configuración para agregar usuarios.")
        st.stop()

    selected_user = st.selectbox("👤 Usuario que solicita", user_names)

    st.markdown("---")

    with st.form("payment_request_form"):
        st.subheader("📋 Información del Pago")

        col1, col2 = st.columns(2)

        with col1:
            # Provider info
            providers = get_providers()
            provider_options = ["-- Seleccionar proveedor existente --"] + [p['name'] for p in providers]
            selected_provider = st.selectbox("🏢 Proveedor", provider_options)

            # Get provider data for defaults
            provider_data = {}
            if selected_provider == "-- Seleccionar proveedor existente --":
                provider_name = st.text_input("Nombre del proveedor *", placeholder="Ej: Proveedor XYZ")
                provider_id = st.text_input("ID del proveedor", placeholder="Ej: PROV-001")
            else:
                provider_name = selected_provider
                provider_data = next((p for p in providers if p['name'] == selected_provider), {})
                provider_id = provider_data.get('provider_id', '')
                st.text_input("ID del proveedor", value=provider_id or "N/A", disabled=True)
                if provider_data.get('payment_condition'):
                    st.info(f"💡 Condición de pago del proveedor: **{provider_data['payment_condition']}**")

            # Orden de Compra
            oc_col1, oc_col2 = st.columns(2)
            with oc_col1:
                oc_type = st.selectbox(
                    "📄 Tipo de OC",
                    ["OC", "OCT", "OCM"],
                    help="OC=Orden de Compra, OCT=OC Terceros, OCM=OC Marketing"
                )
            with oc_col2:
                oc_number = st.text_input("# Orden de Compra", placeholder="Ej: 001234")

            # Nota de Pedido
            np_col1, np_col2 = st.columns(2)
            with np_col1:
                np_type = st.selectbox(
                    "📋 Tipo de NP *",
                    ["NPA", "NPV", "NPW", "NPM"],
                    help="NPA=Administrativo, NPV=Ventas, NPW=Web, NPM=Marketing"
                )
            with np_col2:
                np_number = st.text_input("# Nota de Pedido *", placeholder="Ej: 001234")

            amount = st.number_input("💵 Monto a pagar *", min_value=0.01, step=0.01, format="%.2f")

        with col2:
            payment_type = st.radio(
                "📊 Tipo de pago *",
                ["Total", "Parcial"],
                horizontal=True
            )

            payment_method = st.selectbox(
                "💳 Método de pago *",
                ["Transferencia", "E-Cheq"]
            )

            # Use provider's payment condition as default if available
            default_payment_term = provider_data.get('payment_condition', '') or ''
            payment_term = st.text_input(
                "⏰ Plazo de pago",
                value=default_payment_term,
                placeholder="Ej: 30 días, inmediato, etc."
            )

            agreed_date = st.date_input(
                "📅 Fecha de pago acordada",
                value=None,
                min_value=date.today()
            )

        st.markdown("---")
        st.subheader("📎 Archivos Adjuntos")

        col3, col4 = st.columns(2)

        with col3:
            mockup_file = st.file_uploader(
                "🖼️ Mockup del trabajo",
                type=['png', 'jpg', 'jpeg', 'pdf'],
                help="Suba una imagen o PDF del trabajo a realizar"
            )

        with col4:
            invoice_file = st.file_uploader(
                "🧾 Factura del proveedor",
                type=['png', 'jpg', 'jpeg', 'pdf'],
                help="Suba la factura emitida por el proveedor"
            )

        st.markdown("---")

        submitted = st.form_submit_button("📤 Enviar Solicitud de Pago", use_container_width=True)

        if submitted:
            # Validation
            if not provider_name:
                st.error("Por favor ingrese el nombre del proveedor.")
            elif not np_number:
                st.error("Por favor ingrese el número de Nota de Pedido.")
            elif amount <= 0:
                st.error("Por favor ingrese un monto válido.")
            else:
                # Save files
                mockup_path = save_uploaded_file(mockup_file, "mockup") if mockup_file else None
                invoice_path = save_uploaded_file(invoice_file, "invoice") if invoice_file else None

                # Build OC string
                oc_full = f"{oc_type}-{oc_number}" if oc_number else None

                # Create request
                request_data = {
                    'provider_name': provider_name,
                    'provider_id': provider_id if provider_id else None,
                    'purchase_order_number': oc_full,
                    'np_type': np_type,
                    'np_number': np_number,
                    'amount': amount,
                    'payment_type': payment_type.lower(),
                    'payment_method': payment_method.lower(),
                    'payment_term': payment_term if payment_term else None,
                    'agreed_payment_date': agreed_date.isoformat() if agreed_date else None,
                    'mockup_path': mockup_path,
                    'invoice_path': invoice_path,
                    'requested_by': selected_user
                }

                request_id = create_payment_request(request_data)

                # Add provider to list if new
                if selected_provider == "-- Seleccionar proveedor existente --" and provider_name:
                    add_provider(provider_name, provider_id)

                st.success(f"✅ Solicitud de pago #{request_id} creada exitosamente!")
                st.balloons()

    # Show recent requests by this user
    st.markdown("---")
    st.subheader("📋 Mis Solicitudes Recientes")

    all_requests = get_payment_requests()
    my_requests = [r for r in all_requests if r['requested_by'] == selected_user][:5]

    if my_requests:
        for req in my_requests:
            with st.expander(f"#{req['id']} - {req['provider_name']} - {format_currency(req['amount'])} - {get_status_badge(req['status'])}"):
                st.write(f"**Fecha:** {req['created_at']}")
                st.write(f"**Orden de Compra:** {req['purchase_order_number'] or 'N/A'}")
                st.write(f"**Método:** {req['payment_method']} | **Tipo:** {req['payment_type']}")
                if req['admin_notes']:
                    st.info(f"**Notas de Admin:** {req['admin_notes']}")
    else:
        st.info("No tienes solicitudes recientes.")


# ============== ADMIN VIEW ==============
elif view == "📊 Admin - Gestionar Pagos":
    st.title("📊 Gestión de Pagos")
    st.markdown("Panel de administración para revisar y procesar solicitudes de pago.")

    # Filters
    col1, col2, col3 = st.columns([2, 2, 2])

    with col1:
        status_filter = st.selectbox(
            "Filtrar por estado",
            ["Todos", "Pendiente Pao", "Aprobado Pao", "En Proceso", "Completado", "Rechazado"]
        )

    with col2:
        sort_by = st.selectbox(
            "Ordenar por",
            ["Más recientes", "Más antiguos", "Mayor monto", "Menor monto"]
        )

    # Get requests
    status_map = {
        "Pendiente Pao": "pendiente",
        "Aprobado Pao": "aprobado_cfo",
        "En Proceso": "en_proceso",
        "Completado": "completado",
        "Rechazado": "rechazado"
    }

    if status_filter == "Todos":
        requests = get_payment_requests()
    else:
        requests = get_payment_requests(status=status_map[status_filter])

    # Sort
    if sort_by == "Más antiguos":
        requests = sorted(requests, key=lambda x: x['created_at'])
    elif sort_by == "Mayor monto":
        requests = sorted(requests, key=lambda x: x['amount'], reverse=True)
    elif sort_by == "Menor monto":
        requests = sorted(requests, key=lambda x: x['amount'])

    st.markdown("---")

    # Summary metrics
    col1, col2, col3, col4, col5 = st.columns(5)

    all_reqs_for_metrics = get_payment_requests()

    with col1:
        pending_cfo = len([r for r in all_reqs_for_metrics if r['status'] == 'pendiente'])
        st.metric("⏳ Pend. Pao", pending_cfo)

    with col2:
        approved_cfo = len([r for r in all_reqs_for_metrics if r['status'] == 'aprobado_cfo'])
        st.metric("✅ Aprob. Pao", approved_cfo)

    with col3:
        in_process_count = len([r for r in all_reqs_for_metrics if r['status'] == 'en_proceso'])
        st.metric("🔄 En Proceso", in_process_count)

    with col4:
        total_pending = sum(r['amount'] for r in all_reqs_for_metrics if r['status'] in ['pendiente', 'aprobado_cfo', 'en_proceso'])
        st.metric("💰 Total Pend.", format_currency(total_pending))

    with col5:
        st.metric("📋 Total", len(requests))

    st.markdown("---")

    # Requests table/cards
    if not requests:
        st.info("No hay solicitudes de pago para mostrar.")
    else:
        for req in requests:
            status_colors = {
                'pendiente': '🟡',
                'aprobado_cfo': '🟢',
                'en_proceso': '🔵',
                'completado': '💚',
                'rechazado': '🔴'
            }

            # Build NP display
            np_display = f"{req.get('np_type', '')}-{req.get('np_number', '')}" if req.get('np_number') else "Sin NP"

            # Build OC display
            oc_display = req.get('purchase_order_number') or "Sin OC"

            with st.expander(
                f"{status_colors.get(req['status'], '⚪')} #{req['id']} | {np_display} | {oc_display} | {req['provider_name']} | "
                f"{format_currency(req['amount'])} | {req['payment_method'].upper()}",
                expanded=(req['status'] in ['pendiente', 'aprobado_cfo'])
            ):
                col1, col2 = st.columns([2, 1])

                with col1:
                    st.markdown("#### 📋 Detalles de la Solicitud")

                    details_col1, details_col2 = st.columns(2)

                    with details_col1:
                        st.write(f"**📋 Nota de Pedido:** {np_display}")
                        st.write(f"**Proveedor:** {req['provider_name']}")
                        st.write(f"**ID Proveedor:** {req['provider_id'] or 'N/A'}")
                        st.write(f"**Orden de Compra:** {req['purchase_order_number'] or 'N/A'}")
                        st.write(f"**Solicitado por:** {req['requested_by']}")
                        st.write(f"**Fecha solicitud:** {req['created_at']}")

                    with details_col2:
                        st.write(f"**Monto:** {format_currency(req['amount'])}")
                        st.write(f"**Tipo de pago:** {req['payment_type'].capitalize()}")
                        st.write(f"**Método:** {req['payment_method'].capitalize()}")
                        st.write(f"**Plazo:** {req['payment_term'] or 'N/A'}")
                        st.write(f"**Fecha acordada:** {req['agreed_payment_date'] or 'N/A'}")

                    # Attachments
                    st.markdown("#### 📎 Archivos Adjuntos")
                    attach_col1, attach_col2 = st.columns(2)

                    with attach_col1:
                        if req['mockup_path'] and os.path.exists(req['mockup_path']):
                            st.write("🖼️ **Mockup:**")
                            if req['mockup_path'].lower().endswith(('.png', '.jpg', '.jpeg')):
                                st.image(req['mockup_path'], width=300)
                            else:
                                with open(req['mockup_path'], 'rb') as f:
                                    st.download_button("Descargar Mockup", f, file_name=os.path.basename(req['mockup_path']))
                        else:
                            st.write("🖼️ Mockup: No adjuntado")

                    with attach_col2:
                        if req['invoice_path'] and os.path.exists(req['invoice_path']):
                            st.write("🧾 **Factura:**")
                            if req['invoice_path'].lower().endswith(('.png', '.jpg', '.jpeg')):
                                st.image(req['invoice_path'], width=300)
                            else:
                                with open(req['invoice_path'], 'rb') as f:
                                    st.download_button("Descargar Factura", f, file_name=os.path.basename(req['invoice_path']))
                        else:
                            st.write("🧾 Factura: No adjuntada")

                with col2:
                    st.markdown("#### ⚡ Acciones")

                    current_status = req['status']

                    # Show current status
                    st.write(f"**Estado actual:** {get_status_badge(current_status)}")

                    # Show CFO approval info if approved
                    if req.get('cfo_approved') and req.get('cfo_approved_by'):
                        st.success(f"✅ Aprobado por CFO: {req['cfo_approved_by']}")
                        if req.get('cfo_approved_at'):
                            st.caption(f"Fecha: {req['cfo_approved_at']}")

                    st.markdown("---")

                    # ===== CFO APPROVAL SECTION =====
                    if current_status == 'pendiente':
                        st.markdown("##### 👩‍💼 Aprobación Pao <3")

                        cfo_col1, cfo_col2 = st.columns(2)
                        with cfo_col1:
                            if st.button("✅ Aprobar", key=f"approve_cfo_{req['id']}", use_container_width=True, type="primary"):
                                if approve_cfo(req['id'], "CFO"):
                                    st.success("✅ Aprobado por CFO!")
                                    st.rerun()

                        with cfo_col2:
                            if st.button("❌ Rechazar", key=f"reject_cfo_{req['id']}", use_container_width=True):
                                reject_reason = st.session_state.get(f"reject_reason_{req['id']}", "")
                                if reject_cfo(req['id'], "CFO", reject_reason):
                                    st.error("Rechazado por CFO")
                                    st.rerun()

                        reject_reason = st.text_input(
                            "Motivo de rechazo (opcional)",
                            key=f"reject_reason_{req['id']}",
                            placeholder="Ingrese motivo si rechaza..."
                        )

                    # ===== TESORERÍA SECTION =====
                    elif current_status == 'aprobado_cfo':
                        st.markdown("##### 💳 Tesorería")
                        st.info("⏳ Listo para emisión de pago")

                        if st.button("🚀 Marcar En Proceso", key=f"to_process_{req['id']}", use_container_width=True, type="primary"):
                            if update_payment_status(req['id'], 'en_proceso'):
                                st.success("Marcado en proceso!")
                                st.rerun()

                    elif current_status == 'en_proceso':
                        st.markdown("##### 💳 Tesorería - Completar Pago")

                        proof_file = st.file_uploader(
                            "📄 Comprobante de pago",
                            type=['png', 'jpg', 'jpeg', 'pdf'],
                            key=f"proof_{req['id']}"
                        )

                        if st.button("✅ Marcar Completado", key=f"complete_{req['id']}", use_container_width=True, type="primary"):
                            proof_path = None
                            if proof_file:
                                proof_path = save_uploaded_file(proof_file, f"proof_{req['id']}")

                            if update_payment_status(req['id'], 'completado', payment_proof_path=proof_path):
                                st.success("✅ Pago completado!")
                                st.rerun()

                    # ===== NOTES (always visible) =====
                    st.markdown("---")
                    admin_notes = st.text_area(
                        "Notas / Comentarios",
                        value=req['admin_notes'] or "",
                        key=f"notes_{req['id']}",
                        placeholder="Agregar notas sobre el pago..."
                    )

                    if st.button("💾 Guardar Notas", key=f"save_notes_{req['id']}"):
                        if update_payment_status(req['id'], current_status, admin_notes=admin_notes):
                            st.success("Notas guardadas!")
                            st.rerun()

                    # Show proof if exists
                    if req['payment_proof_path'] and os.path.exists(req['payment_proof_path']):
                        st.markdown("---")
                        st.write("📄 **Comprobante adjunto:**")
                        with open(req['payment_proof_path'], 'rb') as f:
                            st.download_button(
                                "Descargar Comprobante",
                                f,
                                file_name=os.path.basename(req['payment_proof_path']),
                                key=f"download_proof_{req['id']}"
                            )


# ============== CALENDAR VIEW ==============
elif view == "📅 Calendario de Pagos":
    st.title("📅 Calendario de Pagos")
    st.markdown("Vista de pagos programados por fecha acordada.")

    # Get all pending/in_process requests with dates
    all_requests = get_payment_requests()
    scheduled_payments = [
        r for r in all_requests
        if r['agreed_payment_date'] and r['status'] in ['pendiente', 'en_proceso']
    ]

    # Month/Year selector
    col1, col2 = st.columns([1, 3])

    with col1:
        today = date.today()
        selected_month = st.selectbox(
            "Mes",
            list(range(1, 13)),
            index=today.month - 1,
            format_func=lambda x: calendar.month_name[x]
        )
        selected_year = st.selectbox(
            "Año",
            list(range(today.year - 1, today.year + 3)),
            index=1
        )

    # Filter payments for selected month
    month_payments = []
    for p in scheduled_payments:
        try:
            payment_date = datetime.strptime(p['agreed_payment_date'], '%Y-%m-%d').date()
            if payment_date.month == selected_month and payment_date.year == selected_year:
                month_payments.append({**p, 'payment_date': payment_date})
        except:
            continue

    # Group by date
    payments_by_date = {}
    for p in month_payments:
        d = p['payment_date']
        if d not in payments_by_date:
            payments_by_date[d] = []
        payments_by_date[d].append(p)

    with col2:
        # Summary for month
        total_month = sum(p['amount'] for p in month_payments)
        st.metric(
            f"Total programado para {calendar.month_name[selected_month]} {selected_year}",
            format_currency(total_month),
            f"{len(month_payments)} pagos"
        )

    st.markdown("---")

    # Calendar grid
    st.subheader(f"📆 {calendar.month_name[selected_month]} {selected_year}")

    # Get calendar for the month
    cal = calendar.Calendar(firstweekday=0)  # Monday first
    month_days = cal.monthdayscalendar(selected_year, selected_month)

    # Header row
    days_header = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    header_cols = st.columns(7)
    for i, day_name in enumerate(days_header):
        header_cols[i].markdown(f"**{day_name}**")

    # Calendar rows
    for week in month_days:
        cols = st.columns(7)
        for i, day in enumerate(week):
            if day == 0:
                cols[i].markdown("")
            else:
                current_date = date(selected_year, selected_month, day)
                day_payments = payments_by_date.get(current_date, [])

                if day_payments:
                    total_day = sum(p['amount'] for p in day_payments)
                    # Day with payments - highlighted
                    cols[i].markdown(
                        f"""<div style="background-color: #e8f5e9; padding: 5px; border-radius: 5px; min-height: 60px;">
                        <strong>{day}</strong><br>
                        <span style="color: #2e7d32; font-size: 0.8em;">💰 {format_currency(total_day)}</span><br>
                        <span style="font-size: 0.7em;">{len(day_payments)} pago(s)</span>
                        </div>""",
                        unsafe_allow_html=True
                    )
                else:
                    # Day without payments
                    is_today = current_date == today
                    bg_color = "#e3f2fd" if is_today else "#f5f5f5"
                    cols[i].markdown(
                        f"""<div style="background-color: {bg_color}; padding: 5px; border-radius: 5px; min-height: 60px;">
                        <strong>{day}</strong>
                        </div>""",
                        unsafe_allow_html=True
                    )

    st.markdown("---")

    # List view of payments for the month
    st.subheader("📋 Detalle de Pagos del Mes")

    if month_payments:
        # Sort by date
        month_payments_sorted = sorted(month_payments, key=lambda x: x['payment_date'])

        for p in month_payments_sorted:
            status_icon = "🟡" if p['status'] == 'pendiente' else "🔵"
            with st.expander(
                f"{status_icon} {p['payment_date'].strftime('%d/%m')} | {p['provider_name']} | {format_currency(p['amount'])}"
            ):
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Proveedor:** {p['provider_name']}")
                    st.write(f"**Orden de Compra:** {p['purchase_order_number'] or 'N/A'}")
                    st.write(f"**Solicitado por:** {p['requested_by']}")
                with col2:
                    st.write(f"**Monto:** {format_currency(p['amount'])}")
                    st.write(f"**Método:** {p['payment_method'].capitalize()}")
                    st.write(f"**Estado:** {get_status_badge(p['status'])}")
    else:
        st.info("No hay pagos programados para este mes.")

    # Upcoming payments (next 7 days)
    st.markdown("---")
    st.subheader("⚠️ Próximos 7 días")

    upcoming = []
    for p in scheduled_payments:
        try:
            payment_date = datetime.strptime(p['agreed_payment_date'], '%Y-%m-%d').date()
            if today <= payment_date <= today + timedelta(days=7):
                upcoming.append({**p, 'payment_date': payment_date})
        except:
            continue

    if upcoming:
        upcoming_sorted = sorted(upcoming, key=lambda x: x['payment_date'])
        for p in upcoming_sorted:
            days_until = (p['payment_date'] - today).days
            urgency = "🔴" if days_until <= 2 else "🟠" if days_until <= 4 else "🟡"
            st.warning(f"{urgency} **{p['payment_date'].strftime('%d/%m/%Y')}** ({days_until} días) - {p['provider_name']} - {format_currency(p['amount'])}")
    else:
        st.success("✅ No hay pagos en los próximos 7 días.")


# ============== CASHFLOW VIEW ==============
elif view == "💹 Cashflow Proyectado":
    st.title("💹 Cashflow Proyectado")
    st.markdown("Proyección simple de salidas de efectivo basada en pagos programados.")

    # Get all pending/in_process requests
    all_requests = get_payment_requests()
    active_payments = [
        r for r in all_requests
        if r['status'] in ['pendiente', 'en_proceso']
    ]

    # Separate payments with and without dates
    with_date = []
    without_date = []

    for p in active_payments:
        if p['agreed_payment_date']:
            try:
                payment_date = datetime.strptime(p['agreed_payment_date'], '%Y-%m-%d').date()
                with_date.append({**p, 'payment_date': payment_date})
            except:
                without_date.append(p)
        else:
            without_date.append(p)

    # Summary metrics
    st.subheader("📊 Resumen General")

    col1, col2, col3, col4 = st.columns(4)

    total_pending = sum(p['amount'] for p in active_payments)
    total_scheduled = sum(p['amount'] for p in with_date)
    total_unscheduled = sum(p['amount'] for p in without_date)

    with col1:
        st.metric("💰 Total Pendiente", format_currency(total_pending))
    with col2:
        st.metric("📅 Con Fecha", format_currency(total_scheduled), f"{len(with_date)} pagos")
    with col3:
        st.metric("❓ Sin Fecha", format_currency(total_unscheduled), f"{len(without_date)} pagos")
    with col4:
        st.metric("📋 Total Pagos", len(active_payments))

    st.markdown("---")

    # Cashflow projection by week/month
    st.subheader("📈 Proyección de Salidas")

    projection_type = st.radio("Ver por:", ["Semanal (próximas 8 semanas)", "Mensual (próximos 6 meses)"], horizontal=True)

    today = date.today()

    if projection_type == "Semanal (próximas 8 semanas)":
        # Weekly projection
        weeks_data = []

        for i in range(8):
            week_start = today + timedelta(weeks=i)
            week_end = week_start + timedelta(days=6)

            week_payments = [
                p for p in with_date
                if week_start <= p['payment_date'] <= week_end
            ]

            week_total = sum(p['amount'] for p in week_payments)
            weeks_data.append({
                'Semana': f"Sem {i+1}: {week_start.strftime('%d/%m')} - {week_end.strftime('%d/%m')}",
                'Monto': week_total,
                'Pagos': len(week_payments)
            })

        df_weeks = pd.DataFrame(weeks_data)

        # Bar chart
        st.bar_chart(df_weeks.set_index('Semana')['Monto'])

        # Table
        df_display = df_weeks.copy()
        df_display['Monto'] = df_display['Monto'].apply(format_currency)
        st.dataframe(df_display, use_container_width=True, hide_index=True)

    else:
        # Monthly projection
        months_data = []

        for i in range(6):
            month_date = today + relativedelta(months=i)
            month_start = month_date.replace(day=1)

            if i < 5:
                month_end = (month_start + relativedelta(months=1)) - timedelta(days=1)
            else:
                month_end = month_start + relativedelta(months=1) - timedelta(days=1)

            month_payments = [
                p for p in with_date
                if month_start <= p['payment_date'] <= month_end
            ]

            month_total = sum(p['amount'] for p in month_payments)
            months_data.append({
                'Mes': f"{calendar.month_name[month_date.month]} {month_date.year}",
                'Monto': month_total,
                'Pagos': len(month_payments)
            })

        df_months = pd.DataFrame(months_data)

        # Bar chart
        st.bar_chart(df_months.set_index('Mes')['Monto'])

        # Table
        df_display = df_months.copy()
        df_display['Monto'] = df_display['Monto'].apply(format_currency)
        st.dataframe(df_display, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Cumulative cashflow
    st.subheader("📉 Cashflow Acumulado")

    if with_date:
        # Sort by date
        sorted_payments = sorted(with_date, key=lambda x: x['payment_date'])

        cumulative_data = []
        running_total = 0

        for p in sorted_payments:
            running_total += p['amount']
            cumulative_data.append({
                'Fecha': p['payment_date'],
                'Pago': p['amount'],
                'Acumulado': running_total,
                'Proveedor': p['provider_name']
            })

        df_cumulative = pd.DataFrame(cumulative_data)

        # Line chart
        chart_data = df_cumulative[['Fecha', 'Acumulado']].copy()
        chart_data['Fecha'] = pd.to_datetime(chart_data['Fecha'])
        chart_data = chart_data.set_index('Fecha')
        st.line_chart(chart_data)

        # Detail table
        st.markdown("#### Detalle de pagos programados")
        df_table = df_cumulative.copy()
        df_table['Fecha'] = df_table['Fecha'].apply(lambda x: x.strftime('%d/%m/%Y'))
        df_table['Pago'] = df_table['Pago'].apply(format_currency)
        df_table['Acumulado'] = df_table['Acumulado'].apply(format_currency)
        st.dataframe(df_table, use_container_width=True, hide_index=True)
    else:
        st.info("No hay pagos con fecha programada para mostrar.")

    # Payments without date
    if without_date:
        st.markdown("---")
        st.subheader("⚠️ Pagos Sin Fecha Programada")
        st.warning(f"Hay {len(without_date)} pagos pendientes sin fecha acordada por un total de {format_currency(total_unscheduled)}")

        for p in without_date:
            st.write(f"- **{p['provider_name']}**: {format_currency(p['amount'])} ({p['payment_method']})")


# ============== SETTINGS VIEW ==============
elif view == "⚙️ Configuración":
    st.title("⚙️ Configuración")

    tab1, tab2 = st.tabs(["👥 Usuarios", "🏢 Proveedores"])

    with tab1:
        st.subheader("Gestión de Usuarios")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Agregar Usuario")
            with st.form("add_user_form"):
                new_user_name = st.text_input("Nombre del usuario")
                new_user_team = st.selectbox("Equipo", ["produccion", "admin"])

                if st.form_submit_button("➕ Agregar Usuario"):
                    if new_user_name:
                        if add_user(new_user_name, new_user_team):
                            st.success(f"Usuario '{new_user_name}' agregado!")
                            st.rerun()
                        else:
                            st.error("El usuario ya existe.")
                    else:
                        st.error("Ingrese un nombre.")

        with col2:
            st.markdown("#### Usuarios Existentes")

            st.write("**Equipo Producción:**")
            prod_users = get_users(team="produccion")
            for u in prod_users:
                col_name, col_delete = st.columns([4, 1])
                with col_name:
                    st.write(f"👤 {u['name']}")
                with col_delete:
                    if st.button("🗑️", key=f"del_user_{u['id']}", help="Eliminar usuario"):
                        delete_user(u['id'])
                        st.rerun()

            st.write("**Equipo Admin:**")
            admin_users = get_users(team="admin")
            for u in admin_users:
                col_name, col_delete = st.columns([4, 1])
                with col_name:
                    st.write(f"👤 {u['name']}")
                with col_delete:
                    if st.button("🗑️", key=f"del_user_{u['id']}", help="Eliminar usuario"):
                        delete_user(u['id'])
                        st.rerun()

    with tab2:
        st.subheader("Gestión de Proveedores")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Agregar Proveedor")
            with st.form("add_provider_form"):
                new_prov_name = st.text_input("Nombre del proveedor")
                new_prov_id = st.text_input("ID del proveedor (opcional)")
                new_prov_payment_condition = st.text_input(
                    "Condición de pago",
                    placeholder="Ej: 30 días, contado, 50% anticipo, etc."
                )

                if st.form_submit_button("➕ Agregar Proveedor"):
                    if new_prov_name:
                        if add_provider(
                            new_prov_name,
                            new_prov_id if new_prov_id else None,
                            new_prov_payment_condition if new_prov_payment_condition else None
                        ):
                            st.success(f"Proveedor '{new_prov_name}' agregado!")
                            st.rerun()
                        else:
                            st.error("El proveedor ya existe.")
                    else:
                        st.error("Ingrese un nombre.")

        with col2:
            st.markdown("#### Proveedores Existentes")
            providers = get_providers()
            if providers:
                df = pd.DataFrame(providers)[['name', 'provider_id', 'payment_condition']]
                df.columns = ['Nombre', 'ID', 'Condición de Pago']
                df = df.fillna('-')
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No hay proveedores registrados.")
