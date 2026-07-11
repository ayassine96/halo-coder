FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY halo/requirements.txt /app/halo/requirements.txt
RUN pip install --no-cache-dir -r halo/requirements.txt

# Copy the HALO Factory Floor application
COPY halo/factory_floor/ /app/halo/factory_floor/
COPY halo/common/ /app/halo/common/
COPY halo/specs/ /app/halo/specs/
COPY halo/__init__.py /app/halo/__init__.py

ENV HALO_FACTORY_FLOOR_PORT=8888
ENV HALO_SUPERVISOR_URL=http://localhost:9090

EXPOSE 8888

CMD ["python", "-m", "uvicorn", "halo.factory_floor.app:app", "--host", "0.0.0.0", "--port", "8888"]