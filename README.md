# DataHire



## Getting started

To make it easy for you to get started with GitLab, here's a list of recommended next steps.

Already a pro? Just edit this README.md and make it your own. Want to make it easy? [Use the template at the bottom](#editing-this-readme)!

## Add your files

* [Create](https://docs.gitlab.com/user/project/repository/web_editor/#create-a-file) or [upload](https://docs.gitlab.com/user/project/repository/web_editor/#upload-a-file) files
* [Add files using the command line](https://docs.gitlab.com/topics/git/add_files/#add-files-to-a-git-repository) or push an existing Git repository with the following command:

```
cd existing_repo
git remote add origin https://gitlab.com/supersourcing/backend/datahire.git
git branch -M main
git push -uf origin main
```

## Integrate with your tools

* [Set up project integrations](https://gitlab.com/supersourcing/backend/datahire/-/settings/integrations)

## Collaborate with your team

* [Invite team members and collaborators](https://docs.gitlab.com/user/project/members/)
* [Create a new merge request](https://docs.gitlab.com/user/project/merge_requests/creating_merge_requests/)
* [Automatically close issues from merge requests](https://docs.gitlab.com/user/project/issues/managing_issues/#closing-issues-automatically)
* [Enable merge request approvals](https://docs.gitlab.com/user/project/merge_requests/approvals/)
* [Set auto-merge](https://docs.gitlab.com/user/project/merge_requests/auto_merge/)

## Test and Deploy

Use the built-in continuous integration in GitLab.

* [Get started with GitLab CI/CD](https://docs.gitlab.com/ci/quick_start/)
* [Analyze your code for known vulnerabilities with Static Application Security Testing (SAST)](https://docs.gitlab.com/user/application_security/sast/)
* [Deploy to Kubernetes, Amazon EC2, or Amazon ECS using Auto Deploy](https://docs.gitlab.com/topics/autodevops/requirements/)
* [Use pull-based deployments for improved Kubernetes management](https://docs.gitlab.com/user/clusters/agent/)
* [Set up protected environments](https://docs.gitlab.com/ci/environments/protected_environments/)

***

# Editing this README

When you're ready to make this README your own, just edit this file and use the handy template below (or feel free to structure it however you want - this is just a starting point!). Thanks to [makeareadme.com](https://www.makeareadme.com/) for this template.

## Suggestions for a good README

Every project is different, so consider which of these sections apply to yours. The sections used in the template are suggestions for most open source projects. Also keep in mind that while a README can be too long and detailed, too long is better than too short. If you think your README is too long, consider utilizing another form of documentation rather than cutting out information.

## Name
Choose a self-explaining name for your project.

## Description
Let people know what your project can do specifically. Provide context and add a link to any reference visitors might be unfamiliar with. A list of Features or a Background subsection can also be added here. If there are alternatives to your project, this is a good place to list differentiating factors.

## Badges

#### Email/Password Auth
- `POST /auth/register` - User registration
- `POST /auth/login` - User login
- `GET /auth/me` - Get current user profile (protected)

#### LinkedIn OAuth
- `GET /auth/linkedin/login` - Initiate LinkedIn OAuth
- `GET /auth/linkedin/callback` - OAuth callback
- `POST /auth/linkedin/complete-registration` - Complete registration
- `GET /auth/linkedin/profile/{temp_token}` - Verify temporary token
- `GET /auth/linkedin/url` - Get authorization URL

### Interactive Documentation
- **Swagger UI**: `http://localhost:8000/api/v1/docs`
- **ReDoc**: `http://localhost:8000/api/v1/redoc`

## LinkedIn OAuth Integration

### Frontend Integration

1. **Initiate OAuth**
   ```javascript
   window.location.href = '/api/v1/auth/linkedin/login?redirect_url=' + 
       encodeURIComponent(window.location.origin + '/auth/linkedin/callback');
   ```

2. **Handle Callback**
   ```javascript
   // Extract from URL: /auth/linkedin/callback?temp_token=xxx&is_new_user=true
   const tempToken = urlParams.get('temp_token');
   const isNewUser = urlParams.get('is_new_user');
   ```

3. **Complete Registration**
   ```javascript
   fetch('/api/v1/auth/linkedin/complete-registration', {
       method: 'POST',
       headers: { 'Content-Type': 'application/json' },
       body: JSON.stringify({
           temporary_token: tempToken,
           role: 'candidate',
           phone: '+1234567890'
       })
   });
   ```

### LinkedIn App Setup

1. Create app at [LinkedIn Developers](https://www.linkedin.com/developers/apps/new)
2. Configure OAuth 2.0 settings
3. Set redirect URI: `http://yourdomain.com/api/v1/auth/linkedin/callback`
4. Add Client ID and Secret to environment variables

## Database Schema

### Users Table
- `id` - UUID primary key
- `email` - Unique email address
- `password_hash` - Bcrypt hash (nullable for OAuth)
- `role` - User role (candidate/employer/admin)
- `auth_provider` - Authentication method (local/linkedin)
- `linkedin_id` - LinkedIn user ID
- `is_active` - Account status
- `is_verified` - Email verification status
- `created_at` - Registration timestamp
- `updated_at` - Last update timestamp

### Related Tables
- `candidates` - Candidate profiles
- `employers` - Employer profiles
- `refresh_tokens` - JWT refresh tokens

## Security Features

### Authentication
- **JWT Tokens** with configurable expiration
- **Refresh Tokens** for persistent sessions
- **Password Hashing** with bcrypt
- **OAuth Security** with state parameters
- **Temporary Tokens** with 15-minute expiry

### Data Protection
- **Input Validation** with Pydantic schemas
- **SQL Injection Prevention** with SQLAlchemy ORM
- **CORS Configuration** for frontend integration
- **Rate Limiting** (implement as needed)

## Development

### Running Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_auth.py
```

### Database Migrations
```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

### Code Structure
```bash
app/
├── api/v1/          # API endpoints
│   ├── auth.py       # Email/password auth
│   ├── linkedin.py    # LinkedIn OAuth
│   └── api.py        # Router aggregation
├── core/              # Core functionality
│   ├── config.py      # Configuration
│   ├── security.py    # JWT utilities
│   └── dependencies.py # FastAPI dependencies
├── models/            # Database models
├── schemas/           # Pydantic schemas
├── services/          # Business logic
└── db/               # Database setup
```

## Production Deployment

### Environment Setup
1. Set `DEBUG=false` in production
2. Use strong `SECRET_KEY`
3. Configure production database
4. Set up SSL/TLS
5. Configure CORS for your domain

### Docker Deployment
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["python", "main.py"]
```

### Environment Variables for Production
```env
DEBUG=false
SECRET_KEY=your-production-secret-key
DATABASE_URL=postgresql://user:pass@prod-db:5432/datahire
LINKEDIN_CLIENT_ID=prod-client-id
LINKEDIN_CLIENT_SECRET=prod-client-secret
LINKEDIN_REDIRECT_URI=https://yourdomain.com/api/v1/auth/linkedin/callback
```

## Contributing

1. Fork the repository
2. Create feature branch
3. Make your changes
4. Add tests for new features
5. Submit pull request

## License
For open source projects, say how it is licensed.

## Project status
If you have run out of energy or time for your project, put a note at the top of the README saying that development has slowed down or stopped completely. Someone may choose to fork your project or volunteer to step in as a maintainer or owner, allowing your project to keep going. You can also make an explicit request for maintainers.
