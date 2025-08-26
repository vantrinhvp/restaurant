import pytz
from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, EmailStr
from typing import List, Dict, Any, Optional, Union
import xmlrpc.client
import ssl
import os
from datetime import datetime, timedelta
import jwt
from collections import defaultdict
# FastAPI app
app = FastAPI(
    title="Odoo REST API",
    description="REST API wrapper for Odoo XML-RPC",
    version="1.0.0"
)

# Security
security = HTTPBearer()

# Pydantic models
class OdooConfig(BaseModel):
    url: str
    db: str
    username: str
    password: str
    port: int = 8069

class SearchRequest(BaseModel):
    domain: List = Field(default_factory=list)
    fields: Optional[List[str]] = None
    limit: Optional[int] = None
    offset: int = 0
    order: Optional[str] = None

class TimeSlot(BaseModel):
    datetime: str
    duration: float
    available: bool

class CreateRequest(BaseModel):
    values: Dict[str, Any]

class UpdateRequest(BaseModel):
    ids: List[int]
    values: Dict[str, Any]

class DeleteRequest(BaseModel):
    ids: List[int]

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int

class OdooResponse(BaseModel):
    success: bool
    data: Any = None
    error: Optional[str] = None
    count: Optional[int] = None

# Appointment-specific models
class CustomerInfo(BaseModel):
    name: str
    email: EmailStr
    phone: Optional[str] = None

class AppointmentCreate(BaseModel):
    appointment_type_id: int
    datetime_str: str  # Format: 'YYYY-MM-DD HH:MM:SS'
    duration: float = 1.0
    customer_info: CustomerInfo
    staff_user_id: Optional[int] = None
    resource_ids: Optional[List[int]] = None
    capacity: int = 1
    phone: Optional[str] = None
    guest_emails: Optional[List[EmailStr]] = None
    questions: Optional[Dict[str, Union[str, int, List[int]]]] = None
    timezone: Optional[str] = "Asia/Saigon"

class AvailabilityRequest(BaseModel):
    date_from: str  # 'YYYY-MM-DD'
    date_to: str    # 'YYYY-MM-DD'
    staff_user_id: Optional[int] = None
    resource_ids: Optional[List[int]] = None
    capacity: int = 1

class AppointmentResponse(BaseModel):
    success: bool
    appointment_id: Optional[int] = None
    access_token: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    appointment_details: Optional[Dict] = None

# Global Odoo connection
odoo_connection = None

class OdooClient:
    def __init__(self, config: OdooConfig):
        self.config = config
        self.common = None
        self.models = None
        self.uid = None
        self.connect()
    
    def connect(self):
        try:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            common_url = f"{self.config.url}/xmlrpc/2/common"
            models_url = f"{self.config.url}/xmlrpc/2/object"
            
            if self.config.url.startswith('https'):
                self.common = xmlrpc.client.ServerProxy(common_url, context=ssl_context)
                self.models = xmlrpc.client.ServerProxy(models_url, context=ssl_context)
            else:
                self.common = xmlrpc.client.ServerProxy(common_url)
                self.models = xmlrpc.client.ServerProxy(models_url)
            
            self.uid = self.common.authenticate(
                self.config.db, self.config.username, self.config.password, {}
            )
            
            if not self.uid:
                raise Exception("Authentication failed")
                
        except Exception as e:
            raise Exception(f"Connection error: {str(e)}")

    def read(self, model: str, ids: List[int], fields: Optional[List[str]] = None, context: Optional[Dict] = None):
        """
        Read data from records by IDs

        :param model: Model name (e.g., 'res.partner')
        :param ids: List of record IDs to read
        :param fields: List of field names to read (if None, reads all fields)
        :param context: Optional context dictionary
        :return: List of dictionaries containing record data
        """
        try:
            kwargs = {}
            if fields:
                kwargs['fields'] = fields
            if context:
                kwargs['context'] = context

            return self.models.execute_kw(
                self.config.db, self.uid, self.config.password,
                model, 'read', [ids], kwargs
            )
        except Exception as e:
            raise Exception(f"Read error: {str(e)}")

    def search(self, model: str, request: SearchRequest):
        try:
            kwargs = {}
            if request.limit:
                kwargs['limit'] = request.limit
            if request.offset:
                kwargs['offset'] = request.offset
            if request.order:
                kwargs['order'] = request.order

            return self.models.execute_kw(
                self.config.db, self.uid, self.config.password,
                model, 'search', [request.domain], kwargs
            )
        except Exception as e:
            raise Exception(f"Search error: {str(e)}")

    def search_read(self, model: str, request: SearchRequest):
        try:
            kwargs = {}
            if request.fields:
                kwargs['fields'] = request.fields
            if request.limit:
                kwargs['limit'] = request.limit
            if request.offset:
                kwargs['offset'] = request.offset
            if request.order:
                kwargs['order'] = request.order
                
            return self.models.execute_kw(
                self.config.db, self.uid, self.config.password,
                model, 'search_read', [request.domain], kwargs
            )
        except Exception as e:
            raise Exception(f"Search error: {str(e)}")
    
    def create(self, model: str, values: Dict, context: Optional[Dict] = None):
        try:
            kwargs = {}
            if context:
                kwargs['context'] = context
            return self.models.execute_kw(
                self.config.db, self.uid, self.config.password,
                model, 'create', [values], kwargs
            )
        except Exception as e:
            raise Exception(f"Create error: {str(e)}")
    
    def update(self, model: str, ids: List[int], values: Dict):
        try:
            return self.models.execute_kw(
                self.config.db, self.uid, self.config.password,
                model, 'write', [ids, values]
            )
        except Exception as e:
            raise Exception(f"Update error: {str(e)}")
    
    def delete(self, model: str, ids: List[int]):
        try:
            return self.models.execute_kw(
                self.config.db, self.uid, self.config.password,
                model, 'unlink', [ids]
            )
        except Exception as e:
            raise Exception(f"Delete error: {str(e)}")
    
    def get_fields(self, model: str):
        try:
            return self.models.execute_kw(
                self.config.db, self.uid, self.config.password,
                model, 'fields_get', []
            )
        except Exception as e:
            raise Exception(f"Fields error: {str(e)}")

# JWT functions
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 60)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

def get_odoo_client():
    global odoo_connection
    if not odoo_connection:
        raise HTTPException(status_code=500, detail="Odoo not configured")
    return odoo_connection


async def get_or_create_customer(odoo: OdooClient, customer_info: CustomerInfo):
    """Tìm hoặc tạo customer"""
    try:
        # Tìm customer theo email
        customers = odoo.search_read('res.partner', SearchRequest(
            domain=[('email', '=', customer_info.email)],
            fields=['id', 'name', 'email', 'phone'],
            limit=1
        ))

        if customers:
            customer = customers[0]
            # Update thông tin nếu cần
            update_vals = {}
            if customer['name'] != customer_info.name:
                update_vals['name'] = customer_info.name
            if customer_info.phone and customer['phone'] != customer_info.phone:
                update_vals['phone'] = customer_info.phone

            if update_vals:
                odoo.update('res.partner', [customer['id']], update_vals)

            return customer['id']
        else:
            # Tạo customer mới
            customer_vals = {
                'name': customer_info.name,
                'email': customer_info.email,
                'phone': customer_info.phone or '',
                'is_company': False,
                'customer_rank': 1,
            }
            return odoo.create('res.partner', customer_vals)

    except Exception as e:
        raise Exception(f"Customer error: {str(e)}")


def get_resources_remaining_capacity(
        odoo: OdooClient,
        appointment_type_id: int,
        slot_start_utc: datetime,
        slot_stop_utc: datetime
):
    """
    Get remaining capacity for each resource of an appointment type in a time slot

    Args:
        odoo: OdooClient instance
        appointment_type_id: ID of appointment type
        slot_start_utc: Start time of the slot
        slot_stop_utc: End time of the slot

    Returns:
        dict: Contains total_capacity_used and resources remaining capacity info
    """
    try:
        # Lấy appointment type và resource ids
        appointment_type = odoo.read('appointment.type', [appointment_type_id],
                                     fields=['resource_ids', 'name'])

        if not appointment_type:
            raise Exception(f"Appointment type with ID {appointment_type_id} not found")

        appointment_type = appointment_type[0]
        resource_ids = appointment_type.get('resource_ids', [])

        if not resource_ids:
            return {
                'appointment_type_id': appointment_type_id,
                'appointment_type_name': appointment_type.get('name'),
                'total_capacity_used': 0,
                'resources_remaining_capacity': {},
                'summary': {
                    'total_resources': 0,
                    'total_capacity_used': 0,
                    'total_remaining_capacity': 0
                }
            }

        # Lấy thông tin về resources (capacity của từng resource)
        resources = odoo.read('appointment.resource', resource_ids,
                              fields=['id', 'name', 'capacity'])

        # Lấy booking lines trong khoảng thời gian
        booking_lines = odoo.search_read('appointment.booking.line', SearchRequest(
            domain=[
                ('appointment_resource_id', 'in', resource_ids),
                ('event_start', '<', slot_stop_utc),
                ('event_stop', '>', slot_start_utc)
            ],
            fields=['appointment_resource_id', 'capacity_used'],
        ))

        # Tính capacity used cho từng resource
        resource_capacity_used = defaultdict(int)
        total_capacity_used = 0

        for booking_line in booking_lines:
            resource_id = booking_line['appointment_resource_id']
            if isinstance(resource_id, list):
                resource_id = resource_id[0]  # Lấy ID từ [id, name]

            capacity_used = booking_line.get('capacity_used', 0) or 0
            resource_capacity_used[resource_id] += capacity_used
            total_capacity_used += capacity_used

        # Tính remaining capacity cho từng resource
        resources_remaining_capacity = {}
        total_remaining_capacity = 0

        for resource in resources:
            resource_id = resource['id']
            resource_capacity = resource.get('capacity', 1) or 1  # Default capacity = 1
            used_capacity = resource_capacity_used.get(resource_id, 0)
            remaining_capacity = max(0, resource_capacity - used_capacity)

            resources_remaining_capacity[resource_id] = {
                'resource_id': resource_id,
                'resource_name': resource.get('name'),
                'total_capacity': resource_capacity,
                'capacity_used': used_capacity,
                'remaining_capacity': remaining_capacity,
                'is_available': remaining_capacity > 0
            }

            total_remaining_capacity += remaining_capacity

        return {
            'appointment_type_id': appointment_type_id,
            'appointment_type_name': appointment_type.get('name'),
            'slot_start_utc': slot_start_utc.isoformat(),
            'slot_stop_utc': slot_stop_utc.isoformat(),
            'total_capacity_used': total_capacity_used,
            'resources_remaining_capacity': resources_remaining_capacity,
            'summary': {
                'total_resources': len(resources),
                'total_capacity_used': total_capacity_used,
                'total_remaining_capacity': total_remaining_capacity,
                'available_resources': len([r for r in resources_remaining_capacity.values()
                                            if r['is_available']])
            }
        }

    except Exception as e:
        raise Exception(f"Error getting resources remaining capacity: {str(e)}")


async def prepare_calendar_event_data(appointment_type: Dict, date_start: datetime, date_end: datetime,
                                      duration: float, name: str, customer: Dict, staff_user: Optional[Dict],
                                      guest_partner_ids: List[int], answer_input_values: List[Dict]) -> Dict:
    """Prepare calendar event data"""

    # Prepare attendees
    partner_ids = [customer['id']]
    if guest_partner_ids:
        partner_ids.extend(guest_partner_ids)

    event_data = {
        'name': f"Appointment: {name}",
        'start': date_start.strftime('%Y-%m-%d %H:%M:%S'),
        'stop': date_end.strftime('%Y-%m-%d %H:%M:%S'),
        'duration': duration,
        'partner_ids': [(6, 0, partner_ids)],
        'appointment_type_id': appointment_type['id'],
        'description': f"Appointment with {name}\nEmail: {customer['email']}\nPhone: {customer.get('phone', '')}",
        'location': appointment_type.get('location', ''),
    }

    # Set responsible user
    if staff_user:
        event_data['user_id'] = staff_user['id']

    # Add answer inputs
    if answer_input_values:
        event_data['appointment_answer_input_ids'] = [(0, 0, vals) for vals in answer_input_values]

    return event_data

# API Endpoints

@app.post("/api/appointments")
async def create_appointment(
        booking: AppointmentCreate, 
        token: dict = Depends(verify_token),
        odoo: OdooClient = Depends(get_odoo_client)):
    """Create a new appointment booking"""
    try:
        # Validate appointment type exists
        appointment_types = odoo.read('appointment.type', [booking.appointment_type_id],
                                     fields=['resource_ids', 'name', 'schedule_based_on', 'appointment_tz'])
        if not appointment_types:
            raise HTTPException(
                status_code=404,
                detail="Appointment type not found"
            )

        appointment_type = appointment_types[0]
        resource_ids = appointment_type.get('resource_ids', [])
        
        # Parse datetime với timezone handling
        try:
            # Lấy timezone từ booking hoặc appointment type hoặc default
            timezone_str = booking.timezone or appointment_type.get('appointment_tz') or 'Asia/Saigon'
            tz = pytz.timezone(timezone_str)
            
            # Parse datetime và localize với timezone
            naive_datetime = datetime.strptime(booking.datetime_str, '%Y-%m-%d %H:%M')
            local_datetime = tz.localize(naive_datetime)
            
            # Chuyển sang UTC để lưu vào Odoo
            start_date_utc = local_datetime.astimezone(pytz.UTC)
            date_end_utc = start_date_utc + timedelta(hours=booking.duration)
            
            # Sử dụng UTC time để check capacity
            resources_remaining_capacity = get_resources_remaining_capacity(
                odoo, appointment_type['id'], start_date_utc, date_end_utc)
            
            if resources_remaining_capacity['summary']['total_remaining_capacity'] < booking.capacity:
                raise HTTPException(
                    status_code=400,
                    detail=f"Not enough capacity available for appointment type {appointment_type['name']}"
                )

        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid datetime: {str(e)}"
            )

        customer_info = CustomerInfo(
            name=booking.customer_info.name,
            email=booking.customer_info.email,
            phone=booking.customer_info.phone
        )

        # Handle customer
        customer_id = await get_or_create_customer(odoo, customer_info)
        guest_partner_ids = []
        
        # Process booking lines - FIXED LOGIC
        booking_line_values = []
        resources = odoo.read('appointment.resource', resource_ids,
                              fields=['id', 'name', 'capacity'])
        asked_capacity = booking.capacity
        
        if appointment_type['schedule_based_on'] == 'resources':
            # TÌM 1 RESOURCE DUY NHẤT CÓ ĐỦ CAPACITY CHO TẤT CẢ GUESTS
            selected_resource = None
            
            for resource in resources:
                resource_id = resource['id']
                resource_capacity_info = resources_remaining_capacity['resources_remaining_capacity'].get(resource_id, {})
                resource_remaining_capacity = resource_capacity_info.get('remaining_capacity', 0)
                
                # Kiểm tra xem resource này có đủ capacity cho toàn bộ booking không
                if resource_remaining_capacity >= asked_capacity:
                    selected_resource = resource
                    break
            
            if not selected_resource:
                # Nếu không có resource nào đủ capacity, tìm resource có capacity lớn nhất
                max_capacity_resource = max(resources, 
                                          key=lambda r: resources_remaining_capacity['resources_remaining_capacity']
                                          .get(r['id'], {}).get('remaining_capacity', 0))
                
                max_remaining = resources_remaining_capacity['resources_remaining_capacity'].get(
                    max_capacity_resource['id'], {}).get('remaining_capacity', 0)
                
                raise HTTPException(
                    status_code=400,
                    detail=f"No single resource can accommodate {asked_capacity} people. "
                           f"Maximum available capacity on one resource: {max_remaining}"
                )
            
            # Tạo 1 BOOKING LINE DUY NHẤT cho resource được chọn
            booking_line_values.append({
                'appointment_resource_id': selected_resource['id'],
                'capacity_reserved': asked_capacity,
                'capacity_used': asked_capacity,
            })

        # Tạo event với UTC time (Odoo sẽ tự động handle timezone display)
        event_vals = {
            'name': f"Đặt bàn {asked_capacity} người: {booking.customer_info.name}",
            'appointment_booker_id': customer_id,
            'start': start_date_utc.strftime('%Y-%m-%d %H:%M:%S'),
            'stop': date_end_utc.strftime('%Y-%m-%d %H:%M:%S'),
            'partner_ids': [(6, 0, [customer_id] + guest_partner_ids)],
            'booking_line_ids': [(0, 0, vals) for vals in booking_line_values],
            'appointment_type_id': booking.appointment_type_id,
            'duration': booking.duration,
            'appointment_status': 'request',
            'location': appointment_type.get('location', 'restaurant, Việt Nam'),
        }

        # Create the event
        context = {
            'mail_notify_author': True,
            'mail_create_nolog': True,
            'mail_create_nosubscribe': True,
            'tz': timezone_str,  # Set timezone context
        }

        event_id = odoo.create('calendar.event', event_vals, context={'context': context})

        created_event = odoo.search_read('calendar.event', SearchRequest(
            domain=[('id', '=', event_id)],
            fields=['id', 'name', 'start', 'stop', 'location', 'access_token'],
            limit=1
        ))[0]
        
        # Convert UTC times back to local timezone for response
        start_utc = datetime.strptime(created_event['start'], '%Y-%m-%d %H:%M:%S')
        stop_utc = datetime.strptime(created_event['stop'], '%Y-%m-%d %H:%M:%S')
        
        start_utc = pytz.UTC.localize(start_utc)
        stop_utc = pytz.UTC.localize(stop_utc)
        
        start_local = start_utc.astimezone(tz)
        stop_local = stop_utc.astimezone(tz)
        
        return AppointmentResponse(
            success=True,
            appointment_id=event_id,
            access_token=created_event.get('access_token'),
            message="Appointment created successfully",
            appointment_details={
                'id': event_id,
                'name': created_event['name'],
                'start_datetime_local': start_local.strftime('%Y-%m-%d %H:%M:%S'),
                'end_datetime_local': stop_local.strftime('%Y-%m-%d %H:%M:%S'),
                'start_datetime_utc': created_event['start'],
                'end_datetime_utc': created_event['stop'],
                'timezone': timezone_str,
                'duration': booking.duration,
                'customer': booking.customer_info.name,
                'capacity': asked_capacity,
                'selected_resource': selected_resource['name'] if selected_resource else None,
                'staff': None,
                'location': created_event.get('location', ''),
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        return AppointmentResponse(
            success=False,
            error=str(e)
        )
    
@app.post("/auth/login", response_model=AuthResponse)
async def login(config: OdooConfig):
    """Authenticate with Odoo and get access token"""
    try:
        global odoo_connection
        odoo_connection = OdooClient(config)
        
        token_data = {
            "sub": config.username,
            "db": config.db
        }
        access_token = create_access_token(token_data)
        
        return AuthResponse(
            access_token=access_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

@app.get("/models/{model}/fields")
async def get_model_fields(
    model: str,
    token: dict = Depends(verify_token),
    odoo: OdooClient = Depends(get_odoo_client)
):
    """Get field definitions for a model"""
    try:
        fields = odoo.get_fields(model)
        return OdooResponse(success=True, data=fields, count=len(fields))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/models/{model}/search")
async def search_records(
    model: str,
    request: SearchRequest,
    token: dict = Depends(verify_token),
    odoo: OdooClient = Depends(get_odoo_client)
):
    """Search and read records from a model"""
    try:
        records = odoo.search_read(model, request)
        return OdooResponse(success=True, data=records, count=len(records))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/models/{model}/create")
async def create_record(
    model: str,
    request: CreateRequest,
    token: dict = Depends(verify_token),
    odoo: OdooClient = Depends(get_odoo_client)
):
    """Create a new record"""
    try:
        record_id = odoo.create(model, request.values)
        return OdooResponse(success=True, data={"id": record_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/models/{model}/update")
async def update_records(
    model: str,
    request: UpdateRequest,
    token: dict = Depends(verify_token),
    odoo: OdooClient = Depends(get_odoo_client)
):
    """Update existing records"""
    try:
        result = odoo.update(model, request.ids, request.values)
        return OdooResponse(success=True, data={"updated": result})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/models/{model}/delete")
async def delete_records(
    model: str,
    request: DeleteRequest,
    token: dict = Depends(verify_token),
    odoo: OdooClient = Depends(get_odoo_client)
):
    """Delete records"""
    try:
        result = odoo.delete(model, request.ids)
        return OdooResponse(success=True, data={"deleted": result})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Convenience endpoints for common models

@app.get("/appointment/{appointment_type_id}")
async def get_appointment_types(
        appointment_type_id: int,
        slot_start_utc: datetime,
        slot_stop_utc: datetime,
        token: dict = Depends(verify_token),
        odoo: OdooClient = Depends(get_odoo_client)
):
    try:
        appointment_type = odoo.read('appointment.type', [appointment_type_id], fields=['resource_ids'])

        if not appointment_type:
            raise HTTPException(status_code=404, detail=f"Appointment type with ID {appointment_type_id} not found")

        appointment_type = appointment_type[0]
        # slot_start_utc = datetime(slot_start_utc)
        # slot_stop_utc = datetime(slot_stop_utc)

        # Sử dụng search_read để lấy dữ liệu
        booking_lines = odoo.search_read('appointment.booking.line', SearchRequest(
            domain=[
                ('appointment_resource_id', 'in', appointment_type.get('resource_ids', [])),
                 ('event_start', '<', slot_stop_utc),
                ('event_stop', '>', slot_start_utc)
            ],
            fields=['appointment_resource_id', 'event_start', 'event_stop', 'capacity_used'],
        ))

        # Group manually bằng Python

        total_capacity_used = 0
        resource_capacity_totals = defaultdict(int)
        resources_booking_lines = defaultdict(list)
        for booking_line in booking_lines:
            # Xử lý Many2one field (có thể là [id, name] hoặc chỉ id)
            resource_id = booking_line['appointment_resource_id']
            if isinstance(resource_id, list):
                resource_id = resource_id[0]  # Lấy ID từ [id, name]
            
            resources_booking_lines[resource_id].append(booking_line)
            capacity_used = booking_line.get('capacity_used', 0) or 0
            total_capacity_used += capacity_used
            resource_capacity_totals[resource_id] += capacity_used

         # Convert to regular dict
        resources_booking_lines = dict(resources_booking_lines)
        resource_capacity_totals = dict(resource_capacity_totals)

        return OdooResponse(
            success=True,
            data={
                'appointment_type': appointment_type,
                'resources_booking_lines': resources_booking_lines,
                'total_capacity_used': total_capacity_used,
                'resource_capacity_totals': resource_capacity_totals,
                'summary': {
                    'total_bookings': len(booking_lines),
                    'total_capacity_used': total_capacity_used,
                    'resources_count': len(resources_booking_lines)
                }
            },
            count=len(resources_booking_lines)
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.utcnow()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)