# Arquitectura de la solución

## Vista general

Financial Sentiment Radar separa responsabilidades en tres capas:

1. **Capa de consumo**: Streamlit en Amazon ECS Fargate expuesto por Application Load Balancer.
2. **Capa de datos**: Amazon S3 para datos crudos, procesados y outputs.
3. **Capa de inteligencia**: pipeline Python para sentimiento/temas/retrieval y Amazon Bedrock opcional para resumen de evidencia.

## Componentes

- **Application Load Balancer**: punto público de acceso HTTP para el usuario final.
- **ECS Fargate Task**: ejecuta el contenedor Docker con Streamlit.
- **Amazon ECR**: almacena la imagen Docker versionada.
- **Amazon S3**: data lake con prefijos `raw/`, `processed/` y `outputs/`.
- **Amazon Bedrock**: servicio opcional para resumir evidencia recuperada por la app.
- **Twitter/X API**: fuente opcional de adquisición live si existe token.
- **IAM Roles**: separan permisos de ejecución ECS, acceso S3 y Bedrock.
- **CloudWatch Logs**: registra eventos y errores de la app.
- **CloudFormation**: define la infraestructura como código en dos stacks.

## Flujo de datos

1. El usuario entra a la URL pública del ALB.
2. El ALB enruta a la task Fargate que corre Streamlit en el puerto 8501.
3. La app carga el dataset procesado desde S3 o usa el sample local inicial.
4. El usuario sube datos o solicita búsqueda live.
5. El pipeline limpia texto, extrae tickers, clasifica sentimiento, asigna tema y deduplica.
6. La app persiste datos procesados en S3.
7. El usuario hace una pregunta; la app recupera evidencia con TF-IDF.
8. Si Bedrock está habilitado, se resume la evidencia; si no, se usa respuesta extractiva local.
9. Logs y errores quedan en CloudWatch.

## Decisiones de diseño

- Se usa Fargate para no administrar servidores.
- Se usa ALB para que el instructor tenga una URL pública estable.
- Se usa S3 como repositorio analítico simple, barato y suficiente para el MVP.
- Se evita NAT Gateway para reducir costos.
- Se mantiene Bedrock como opcional para controlar presupuesto.
- Se usa un scorer ligero para no depender de GPU ni modelos pesados.

## Seguridad

- No se guardan credenciales en código.
- El bucket bloquea acceso público y usa cifrado SSE-S3.
- La task tiene IAM Role con permisos acotados a S3 y Bedrock.
- Twitter/X bearer token se debe pasar como secreto de Secrets Manager si se usa.
- Los logs no imprimen tokens ni datos sensibles.

## Escalabilidad y evolución

Para producción real se recomienda mover tareas a subnets privadas, agregar VPC endpoints, Cognito, scheduled ingestion con EventBridge, almacenamiento operacional para feedback y modelo NLP administrado en SageMaker/Bedrock.
