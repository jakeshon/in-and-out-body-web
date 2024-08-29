# analysis/views.py

import os
import re
import uuid
import pandas as pd
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from rest_framework import permissions, viewsets
from django.contrib.auth.hashers import make_password, check_password
from rest_framework import viewsets, permissions
from rest_framework.response import Response
from django.contrib.auth.views import PasswordChangeView


from .helpers import parse_userinfo
from .models import AuthInfo, BodyResult, GaitResult, SchoolInfo, UserInfo, SessionInfo
from .forms import UploadFileForm, CustomPasswordChangeForm
from .serializers import BodyResultSerializer, GaitResultSerializer, UserInfoSerializer


from rest_framework.decorators import api_view, action
from rest_framework.response import Response

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

def home(request):
    if request.user.is_authenticated:
        return redirect('register_student')
    else:
        return redirect('login')

@login_required
def register_student(request):
    users = []  # Initialize an empty list to hold user data

    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            excel_file = request.FILES['file']
            # Read the Excel file
            df = pd.read_excel(excel_file)
            
            for _, row in df.iterrows():
                    
                school_info, created = SchoolInfo.objects.update_or_create(
                    school_name=row['학교'],
                )
                
                # Find or create the UserInfo
                user_info, created = UserInfo.objects.update_or_create(
                    username=row['전화번호'].strip().replace('-', ''),
                    defaults=dict(
                        school=school_info,
                        student_grade=row['학년'],
                        student_class=row['반'],
                        student_number=row['번호'],
                        student_name=row['이름'].strip().replace(' ', ''),
                        phone_number=row['전화번호'].strip().replace('-', ''),
                        password=make_password(os.environ['DEFAULT_PASSWORD'])
                    ),
                )

                users.append(user_info)


            return render(request, 'register_student.html', {
                'form': form,
                'users': users
            })
    else:
        form = UploadFileForm()
    
    return render(request, 'register_student.html', {'form': form})

@login_required
def report(request):
    groups = UserInfo.objects.values_list('student_grade', 'student_class', named=True).distinct().order_by('student_grade', 'student_class')
    groups = [ f'{g.student_grade}학년 {g.student_class}반' for g in groups if ((g.student_grade is not None) & (g.student_class is not None)) ] # Note : 학년, 반 정보 없는 superuser는 그룹에 포함안됨
    
    if request.method == 'POST':
        selected_group = request.POST.get('group')

        # 정규 표현식을 사용하여 학년과 반 추출
        match = re.search(r"(\d+)학년 (\d+)반", selected_group)
        users = UserInfo.objects.filter(student_grade=match.group(1), 
                                        student_class=match.group(2))
    else:
        users = UserInfo.objects.none()
        selected_group = None
    return render(request, 'report.html', {'groups': groups, 'users': users, 'selected_group': selected_group})

def policy(request):
    return render(request, 'policy.html')


class UserInfoViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    """
    queryset = UserInfo.objects.all().order_by('-created_dt')
    serializer_class = UserInfoSerializer
    permission_classes = [permissions.IsAuthenticated]

from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

class GaitResultViewSet(viewsets.ViewSet):
    queryset = GaitResult.objects.all().order_by('-created_dt')
    serializer_class = GaitResultSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Create a new gait analysis result record",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'session_key': openapi.Schema(type=openapi.TYPE_STRING, description='Session key for the user'),
                'gait_data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'velocity': openapi.Schema(type=openapi.TYPE_NUMBER, description='Velocity'),
                        'cadence': openapi.Schema(type=openapi.TYPE_NUMBER, description='Cadence'),
                        'cycle_time_l': openapi.Schema(type=openapi.TYPE_NUMBER, description='Cycle time left'),
                        'cycle_time_r': openapi.Schema(type=openapi.TYPE_NUMBER, description='Cycle time right'),
                        'stride_len_l': openapi.Schema(type=openapi.TYPE_NUMBER, description='Stride length left'),
                        'stride_len_r': openapi.Schema(type=openapi.TYPE_NUMBER, description='Stride length right'),
                        'supp_base_l': openapi.Schema(type=openapi.TYPE_NUMBER, description='Support base left'),
                        'supp_base_r': openapi.Schema(type=openapi.TYPE_NUMBER, description='Support base right'),
                        'swing_perc_l': openapi.Schema(type=openapi.TYPE_NUMBER, description='Swing percentage left'),
                        'swing_perc_r': openapi.Schema(type=openapi.TYPE_NUMBER, description='Swing percentage right'),
                        'stance_perc_l': openapi.Schema(type=openapi.TYPE_NUMBER, description='Stance percentage left'),
                        'stance_perc_r': openapi.Schema(type=openapi.TYPE_NUMBER, description='Stance percentage right'),
                        'd_supp_perc_l': openapi.Schema(type=openapi.TYPE_NUMBER, description='Double support percentage left'),
                        'd_supp_perc_r': openapi.Schema(type=openapi.TYPE_NUMBER, description='Double support percentage right'),
                        'toeinout_l': openapi.Schema(type=openapi.TYPE_NUMBER, description='Toe-in/out angle left'),
                        'toeinout_r': openapi.Schema(type=openapi.TYPE_NUMBER, description='Toe-in/out angle right'),
                        'stridelen_cv_l': openapi.Schema(type=openapi.TYPE_NUMBER, description='Stride length coefficient of variation left'),
                        'stridelen_cv_r': openapi.Schema(type=openapi.TYPE_NUMBER, description='Stride length coefficient of variation right'),
                        'stridetm_cv_l': openapi.Schema(type=openapi.TYPE_NUMBER, description='Stride time coefficient of variation left'),
                        'stridetm_cv_r': openapi.Schema(type=openapi.TYPE_NUMBER, description='Stride time coefficient of variation right'),
                        'score': openapi.Schema(type=openapi.TYPE_NUMBER, description='Gait score'),
                    }
                ),
            },
            required=['session_key', 'gait_data'],
        ),
        responses={
            200: openapi.Response(description='Created', schema=GaitResultSerializer),
        },
        tags=['gait-analysis']
    )
    @action(detail=False, methods=['post'])
    def create_result(self, request):
        session_key = request.data.get('session_key')
        if not session_key:
            return Response({'message': 'session_key_required'})

        try:
            session_info = SessionInfo.objects.get(session_key=session_key)
        except SessionInfo.DoesNotExist:
            return Response({'message': 'session_key_not_found'})

        try:
            user_info = UserInfo.objects.get(id=session_info.user_id)
        except UserInfo.DoesNotExist:
            return Response({'message': 'user_not_found'})

        # Retrieve or create a fixed "null school" instance
        null_school, created = SchoolInfo.objects.get_or_create(
            id=-1,
            school_name='null', 
            contact_number='null'
        )

        data = request.data.copy()
        if user_info.school is None:
            data['school'] = null_school.id
        
        data['user'] = user_info.id
        serializer = GaitResultSerializer(data=data)
        
        if serializer.is_valid():
            serializer.save()
            return Response({'message': 'created_gait_result'})
        else:
            return Response({'message' : serializer.errors})

    @swagger_auto_schema(
        operation_description="Retrieve gait analysis results by session key",
        manual_parameters=[
            openapi.Parameter('id', openapi.IN_QUERY, description="Record ID", type=openapi.TYPE_INTEGER),
        ],
        responses={
            200: GaitResultSerializer(many=True),
        },
        tags=['gait-analysis']
    )
    @action(detail=False, methods=['get'])
    def get_result(self, request):
        user_id = request.user.id
        gait_results = GaitResult.objects.filter(user_id=user_id)
        id = self.request.query_params.get('id', None)
        if id is not None:
            gait_results = gait_results.filter(id=id)
        if not gait_results.exists():
            return Response({"message": "gait_result_not_found"})
                
        # Serialize the GaitResult objects
        serializer = GaitResultSerializer(gait_results, many=True)

        return Response({'data': serializer.data})
        
class BodyResultViewSet(viewsets.ViewSet):
    queryset = BodyResult.objects.all().order_by('-created_dt')
    serializer_class = BodyResultSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @swagger_auto_schema(
        operation_description="Create a new body result record",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'session_key': openapi.Schema(type=openapi.TYPE_STRING, description='Session key for the user'),
                'body_data': openapi.Schema(
                    type=openapi.TYPE_OBJECT,
                    properties={
                        'face_level_angle': openapi.Schema(type=openapi.TYPE_NUMBER, description='Face level angle'),
                        'shoulder_level_angle': openapi.Schema(type=openapi.TYPE_NUMBER, description='Shoulder level angle'),
                        'hip_level_angle': openapi.Schema(type=openapi.TYPE_NUMBER, description='Hip level angle'),
                        'leg_length_ratio': openapi.Schema(type=openapi.TYPE_NUMBER, description='Leg length ratio'),
                        'left_leg_alignment_angle': openapi.Schema(type=openapi.TYPE_NUMBER, description='Left leg alignment angle'),
                        'right_leg_alignment_angle': openapi.Schema(type=openapi.TYPE_NUMBER, description='Right leg alignment angle'),
                        'left_back_knee_angle': openapi.Schema(type=openapi.TYPE_NUMBER, description='Left back knee angle'),
                        'right_back_knee_angle': openapi.Schema(type=openapi.TYPE_NUMBER, description='Right back knee angle'),
                        'forward_head_angle': openapi.Schema(type=openapi.TYPE_NUMBER, description='Forward head angle'),
                        'scoliosis_shoulder_ratio': openapi.Schema(type=openapi.TYPE_NUMBER, description='Scoliosis shoulder ratio'),
                        'scoliosis_hip_ratio': openapi.Schema(type=openapi.TYPE_NUMBER, description='Scoliosis hip ratio'),
                        })
            },
            required=['session_key'],  # Add any required fields here
        ),
        responses={
            200: openapi.Response('Created', BodyResultSerializer),
        },
        tags=['body-analysis']
    )
    @action(detail=False, methods=['post'])
    def create_result(self, request):
        session_key = request.data.get('session_key')
        if not session_key:
            return Response({'message': 'session_key_required'})
        
        try:
            session_info = SessionInfo.objects.get(session_key=session_key)
        except SessionInfo.DoesNotExist:
            return Response({'message': 'session_key_not_found'})

        try:
            user_info = UserInfo.objects.get(id=session_info.user_id)
        except UserInfo.DoesNotExist:
            return Response({'message': 'user_not_found'})

        # Retrieve or create a fixed "null school" instance
        null_school, created = SchoolInfo.objects.get_or_create(
            id=-1,
            school_name='null', 
            contact_number='null'
        )

        data = request.data.copy()
        if user_info.school is None:
            data['school'] = null_school.id
        
        data['user'] = user_info.id
        serializer = BodyResultSerializer(data=data)
        
        if serializer.is_valid():
            serializer.save()
            return Response({'message': 'created_body_result'})
        else:
            return Response({'message' : serializer.errors})

    @swagger_auto_schema(
        operation_description="Retrieve body analysis results by session key",
        manual_parameters=[
            openapi.Parameter('id', openapi.IN_QUERY, description="Record ID", type=openapi.TYPE_INTEGER),
        ],
        responses={
            200: BodyResultSerializer(many=True),
        },
        tags=['body-analysis']
    )
    @action(detail=False, methods=['get'])
    def get_result(self, request):
        user_id = request.user.id
        body_results = BodyResult.objects.filter(user_id=user_id)
        id = self.request.query_params.get('id', None)
        if id is not None:
            body_results = body_results.filter(id=id)

        if not body_results.exists():
            return Response({"message": "body_result_not_found"})
                
        # Serialize the BodyResult objects
        serializer = BodyResultSerializer(body_results, many=True)
        return Response({'data': serializer.data})
    
class CustomPasswordChangeView(PasswordChangeView):
    form_class = CustomPasswordChangeForm
    template_name = 'password_change.html'
    success_url = '/password-change-done/'

@swagger_auto_schema(
    method='post',
    operation_description="Authenticate mobile device using mobile_uid",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'mobile_uid': openapi.Schema(type=openapi.TYPE_STRING, description='Unique identifier for the mobile device'),
        },
        required=['mobile_uid'],
    ),
    responses={
        200: openapi.Response('Success', openapi.Schema(type=openapi.TYPE_OBJECT, 
                                                        properties={
                                                            'data': 
                              openapi.Schema(
                                type=openapi.TYPE_OBJECT,
                                properties={
                                    'user_info': openapi.Schema(type=openapi.TYPE_OBJECT, description='User information'),
                                    'jwt_tokens': openapi.Schema(
                                        type=openapi.TYPE_OBJECT,
                                        properties={
                                            'access_token': openapi.Schema(type=openapi.TYPE_STRING, description='Access token'),
                                            'refresh_token': openapi.Schema(type=openapi.TYPE_STRING, description='Refresh token'),
                                        }
                                    ),
                                    'message': openapi.Schema(type=openapi.TYPE_STRING, description='Success message'),
                                }
                            )})),
    }
)
@api_view(['POST'])
def auth_mobile(request):
    mobile_uid = request.data.get('mobile_uid')
    if not mobile_uid:
        return Response({'message': 'mobile_uid_required'})
    
    try:
        auth_info = AuthInfo.objects.get(uid=mobile_uid)
    except AuthInfo.DoesNotExist:
        return Response(
            {
                'message': 'user_not_found'
            })
                    
    authorized_user_info, user_created = UserInfo.objects.update_or_create(
                                    phone_number=auth_info.phone_number,
                                    defaults=dict(
                                        username=auth_info.phone_number,
                                        password=make_password(os.environ['DEFAULT_PASSWORD']),
                                    ))
        
    authorized_user_info.user_type = 'G' if authorized_user_info.school is None else 'S'
    if authorized_user_info.user_type == 'G':
        authorized_user_info.username = f'test_{authorized_user_info.id}'

    authorized_user_info.save()

    token = TokenObtainPairSerializer.get_token(authorized_user_info)
    refresh_token = str(token)
    access_token = str(token.access_token)

    data_obj = {
        'data': {
            'user_info': parse_userinfo(authorized_user_info),
            'jwt_tokens':{
                'access_token': access_token,
                'refresh_token': refresh_token,
            },
            'message': 'success',
        }
    }

    auth_info.delete()
    
    return Response({'data' : {k: v for k, v in data_obj.items() if v is not None}})

@swagger_auto_schema(
    method='post',
    operation_description="Login to the kiosk using kiosk_id, returning session key",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'kiosk_id': openapi.Schema(type=openapi.TYPE_STRING, description='Kiosk identifier'),
        },
        required=['kiosk_id'],
    ),
    responses={
        200: openapi.Response('Success', openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={'data': 
                        openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'session_key': openapi.Schema(type=openapi.TYPE_STRING, description='Generated session key'),
                            }
        )})  ),
    }
)
@api_view(['POST'])
def login_kiosk(request):
    kiosk_id = request.data.get('kiosk_id')
    if not kiosk_id:
        return Response({'message': 'kiosk_id_required'})
    
    # POST 메소드를 사용하여 키오스크 로그인 요청 처리
    session_key = uuid.uuid4().hex
    SessionInfo.objects.update_or_create(
        session_key=session_key,
        kiosk_id=kiosk_id,
    )

    return Response({'data' : {'session_key': session_key}})

@swagger_auto_schema(
    method='post',
    operation_description="Login using session-key-generated QR code in mobile app",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'session_key': openapi.Schema(type=openapi.TYPE_STRING, description='Session key from QR code'),
            'user_id': openapi.Schema(type=openapi.TYPE_STRING, description='User ID'),
        },
        required=['session_key', 'user_id'],
    ),
    responses={
        200: openapi.Response('Login Success', 
                              openapi.Schema(type=openapi.TYPE_OBJECT, properties={
                                  'data': 
                               openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'session_key': openapi.Schema(type=openapi.TYPE_STRING, description='Session key'),
                'message': openapi.Schema(type=openapi.TYPE_STRING, description='Success message'),
            }
        )})),
    }
)
@api_view(['POST'])
def login_mobile_qr(request):
    session_key = request.data.get('session_key')
    if not session_key:
        return Response({'message': 'session_key_required'})
    
    user_id = request.data.get('user_id')
    if not user_id:
        return Response({'message': 'user_id_required'})

    try:
        session_info = SessionInfo.objects.get(session_key=session_key)
    except SessionInfo.DoesNotExist:
        return Response(
            {
                'message': 'session_key_not_found'
            })

    session_info.user_id = user_id
    session_info.save()

    return Response({'data': {'session_key': session_key, 'message': 'login_success'}})

@swagger_auto_schema(
    method='post',
    operation_description="Login to the kiosk using session key, phone number, and password",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'session_key': openapi.Schema(type=openapi.TYPE_STRING, description='Session key'),
            'phone_number': openapi.Schema(type=openapi.TYPE_STRING, description='Phone number'),
            'password': openapi.Schema(type=openapi.TYPE_STRING, description='Password'),
        },
        required=['session_key', 'phone_number', 'password'],
    ),
    responses={
        200: openapi.Response('Login Success', 
                              openapi.Schema(type=openapi.TYPE_OBJECT, 
                                            properties={
                                                        'data' : openapi.Schema(
                                                                    type=openapi.TYPE_OBJECT,
                                                                    properties={
                                                                        'session_key': openapi.Schema(type=openapi.TYPE_STRING, description='Session key'),
                                                                        'message': openapi.Schema(type=openapi.TYPE_STRING, description='Success message'),
                                                                    }
                                                                )}),),
    }
)
@api_view(['POST'])
def login_kiosk_id(request):
    session_key = request.data.get('session_key')
    if not session_key:
        return Response({'message': 'session_key_required'})
    
    phone_number = request.data.get('phone_number')
    password = request.data.get('password')
    
    if not phone_number or not password:
        return Response({'message': 'phone_number_and_password_required'})

    try:
        session_info = SessionInfo.objects.get(session_key=session_key)
    except SessionInfo.DoesNotExist:
        return Response(
            {
                'message': 'session_key_not_found',
            })

    try:
        user_info = UserInfo.objects.get(id=session_info.user_id)
    except UserInfo.DoesNotExist:
        return Response({"message": "user_not_found"},
                )
        
    if check_password(password, user_info.password) and (phone_number == user_info.phone_number):
        return Response({'data' : {'session_key': session_key, 'message': 'login_success'}})
    else:
        return Response({'data': {'session_key': session_key, 'message': 'incorrect_password'}})

@swagger_auto_schema(
    method='get',
    operation_description="Retrieve user information by session key",
    manual_parameters=[
        openapi.Parameter('session_key', openapi.IN_QUERY, description="Session key", type=openapi.TYPE_STRING),
    ],
    responses={
        200: openapi.Response('Success', openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'data': openapi.Schema(
                            type=openapi.TYPE_OBJECT,
                            properties={
                                'user_info': openapi.Schema(type=openapi.TYPE_OBJECT, description='User information'),
                            }
                        )})),
    }
)
@api_view(['GET'])
def get_userinfo_session(request):
    session_key = request.query_params.get('session_key')
    if not session_key:
        return Response({'message': 'session_key_required'})
    try:
        session_info = SessionInfo.objects.get(session_key=session_key)
    except SessionInfo.DoesNotExist:
        return Response(
            {
                'message': 'session_key_not_found',
            })
    
    try:
        user_info = UserInfo.objects.get(id=session_info.user_id)
    except UserInfo.DoesNotExist:
        return Response({"message": "user_not_found"},
                )
    
    return Response({'data' : {k: v for k, v in parse_userinfo(user_info).items() if v is not None}})

@swagger_auto_schema(
    method='post',
    operation_description="End the session using session key",
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        properties={
            'session_key': openapi.Schema(type=openapi.TYPE_STRING, description='Session key'),
        },
        required=['session_key'],
    ),
    responses={
        200: openapi.Response('Success', openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                'message': openapi.Schema(type=openapi.TYPE_STRING, description='Success message'),
            }
        )),
    }
)
@api_view(['POST'])
def end_session(request):
    session_key = request.data.get('session_key')
    if not session_key:
        return Response({'message': 'session_key_required'})
    try:
        session_info = SessionInfo.objects.get(session_key=session_key)
    except SessionInfo.DoesNotExist:
        return Response(
            {
                'message': 'session_key_not_found',
            })
    
    session_info.delete()
    return Response({'message': 'session_closed'})
