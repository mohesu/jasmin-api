FROM python:2.7-alpine

RUN apk add bash

COPY . .

RUN pip install -r requirements.txt

EXPOSE 8000 8080

ENTRYPOINT ["/entrypoint.sh"]

CMD ["python", "/jasmin_api/run_cherrypy.py"]