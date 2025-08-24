FROM python:3.11-slim

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt
RUN playwright install --with-deps

COPY ./oddo.py /code/

CMD ["fastapi", "run", "oddo.py", "--port", "80"]