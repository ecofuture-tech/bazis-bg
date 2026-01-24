# Bazis-BG

[![PyPI version](https://img.shields.io/pypi/v/bazis-bg.svg)](https://pypi.org/project/bazis-bg/)
[![Python Versions](https://img.shields.io/pypi/pyversions/bazis-bg.svg)](https://pypi.org/project/bazis-bg/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Background task package for the Bazis framework. Provides an asynchronous task management system with scheduler support, handlers, periodic tasks, and specialized classes for data import/export.

## Quick Start

```bash
# Install package
uv add bazis-bg

# Create task
from bazis.contrib.bg.basic.base import BgBase

class MyTask(BgBase):
    name = 'My Task'
    
    def handle(self):
        self.next_phase('Processing', expected=100)
        for i in range(100):
            self.progress(d_count=10)

# Run task
task = MyTask.delay()

# Start scheduler
python manage.py bg_scheduler
```

## Table of Contents

- [Description](#description)
- [Core Concept](#core-concept)
- [Features](#features)
- [Requirements](#requirements)
- [Installation](#installation)
- [Architecture](#architecture)
- [Usage](#usage)
  - [Creating Basic Task](#creating-basic-task)
  - [Running Tasks](#running-tasks)
  - [Periodic Tasks](#periodic-tasks)
  - [Data Export](#data-export)
  - [Data Import](#data-import)
- [Task API](#task-api)
- [Configuration](#configuration)
- [Task Management](#task-management)
- [Examples](#examples)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)
- [Links](#links)

## Description

**Bazis-BG** is an extension for the Bazis framework that provides a powerful background task management system. The package is built on top of Django ORM and provides a distributed task processing system with support for:

- Asynchronous task execution
- Task scheduler (cron-like)
- Multiple handlers
- Progress tracking
- Specialized classes for data import/export
- Management through Django admin panel

## Core Concept

The background task system in **Bazis-BG** consists of three main components:

1. **Scheduler** (`bg_scheduler`) - monitors tasks in the database and manages handlers
2. **Handlers** (`bg_handler`) - execute tasks in separate processes
3. **Tasks** - classes inheriting from `BgBase` containing business logic

When an application calls `Task.delay()`, a record is created in the database. The scheduler discovers the new task and passes it to a free handler. The handler executes the task in an isolated process, updating status and progress in the database.

This approach provides:
- Task execution isolation
- Scalability through adding handlers
- Fault tolerance - tasks are not lost if a handler crashes
- Transparency - complete information about execution state

## Features

- **Distributed processing**: Multiple handlers for parallel task execution
- **Scheduler**: Support for periodic tasks with cron syntax and intervals
- **Progress tracking**: Detailed information about task execution state
- **Execution history**: Saving execution phases with timestamps
- **Logging**: Built-in logging system for each task
- **Task interruption**: Ability to interrupt a running task
- **Transactions**: Support for transactional execution
- **Files**: Working with files (upload/download)
- **Specialized classes**:
  - `BgBaseDownload` — data export to Excel
  - `BgBaseLoad` — data import from Excel/ZIP
  - `BgBaseDownloadModel` — Django model export
- **Healthcheck**: Monitoring scheduler and handler health

## Advantages Over Other Solutions

1. **Django Integration**: Uses Django ORM, migrations, and admin
2. **Ease of Use**: Minimal code to create tasks
3. **Transparency**: Complete execution information through admin
4. **Specialized Classes**: Ready solutions for import/export
5. **Distribution**: Easy scaling through adding handlers

## Requirements

- **Python**: 3.12+
- **Bazis**: base package must be installed
- **PostgreSQL**: 12+
- **Redis**: for caching
- **Dependencies**:
  - `openpyxl` — working with Excel files
  - `psutil` — process management
  - `crontab` — parsing cron expressions
  - `aiohttp` — asynchronous HTTP requests

> **Note!** The current framework implementation requires **Redis** as the cache backend and **PostgreSQL** as the database.

## Installation

### Using uv (recommended)

```bash
uv add bazis-bg
```

### Using pip

```bash
pip install bazis-bg
```

### For Development

```bash
git clone git@github.com:ecofuture-tech/bazis-bg.git
cd bazis-bg
uv sync --dev
```

### Project Setup

1. **Add application to Django settings:**

```python
INSTALLED_APPS = [
    # ...
    'bazis.contrib.bg',
    # ...
]
```

2. **Apply migrations:**

```bash
python manage.py migrate
```

3. **Configure environment variables:**

```bash
# Scheduler
BS_TASK_SCHEDULER_HOST=localhost
BS_TASK_SCHEDULER_PORT=8099
BS_TASK_SCHEDULER_IDLE=1

# Handlers
BS_TASK_HANDLERS_LOCAL=3
BS_TASK_HANDLER_PORT=8100
BS_TASK_HANDLER_IDLE=1

# Storage
BS_TASK_FOLDER=bg/tasks
```

## Architecture

### System Components

```
┌─────────────────┐
│   Application   │ ──> delay() ──> Create Task
└─────────────────┘
         │
         ▼
┌─────────────────┐
│   Scheduler     │ ──> Monitor tasks
│  (bg_scheduler) │ ──> Start handlers
└─────────────────┘
         │
         ▼
┌─────────────────┐
│    Handlers     │ ──> Execute Task
│  (bg_handler)   │ ──> Update status
└─────────────────┘
```

### Models

- **Task** — main task model
- **TaskCron** — periodic task model
- **TaskHandler** — handler model

### Task States

1. `draft` — Draft
2. `waiting` — Waiting to start
3. `starting` — Starting
4. `running` — Running
5. `done` — Completed

### Package Structure

```
bazis.contrib.bg/
├── basic/
│   ├── base.py              # Base BgBase class
│   ├── base_download.py     # Data export class
│   ├── base_download_model.py  # Django model export
│   └── base_load.py         # Data import class
├── models_abstract.py       # Abstract models
├── models.py                # Concrete models
├── admin.py                 # Django admin
└── management/
    └── commands/
        ├── bg_scheduler.py  # Scheduler command
        └── bg_handler.py    # Handler command
```

## Usage

### Creating Basic Task

```python
from bazis.contrib.bg.basic.base import BgBase

class DataProcessingTask(BgBase):
    # Human-readable task name
    name = 'Data Processing'
    
    # Number of simultaneously running tasks
    parallel = 2
    
    # Tasks that block execution
    blocked = ['myapp.tasks.AnotherTask']
    
    # Execute in transaction
    is_transaction = True
    
    def pre_handle(self):
        """Called before handle()"""
        self.log.info('Preliminary preparation')
    
    def handle(self):
        """Main task logic"""
        # Set phase with expectation
        self.next_phase('Loading data', expected=1000)
        
        for i in range(1000):
            # Your logic
            
            # Update progress
            self.progress(
                performed=i+1,  # Performed
                d_time=3,       # Sync every 3 sec
                d_count=100     # Or every 100 operations
            )
        
        # Next phase
        self.next_phase('Saving results', expected=100)
        
        # ... save logic
        
        # Save result
        self.set_result({'processed': 1000, 'saved': 100})
    
    def post_handle(self):
        """Called after handle()"""
        self.log.info('Finalization')
    
    def excepting(self):
        """Exception handling"""
        self.log.error('An error occurred')
    
    def interrupting(self):
        """Interruption handling"""
        self.log.warning('Task interrupted by user')
    
    def finishing(self):
        """Always executed at the end"""
        self.log.info('Resource cleanup')
```

### Running Tasks

#### Asynchronous Launch

```python
# Basic launch
task = DataProcessingTask.delay()

# With parameters
task = DataProcessingTask.delay(
    param1='value1',
    param2='value2'
)

# With custom name
task = DataProcessingTask.delay(
    name='January data processing',
    param1='value1'
)

# With file
with open('data.xlsx', 'rb') as fp:
    task = DataProcessingTask.delay(
        fp=fp,
        param1='value1'
    )

# With author
task = DataProcessingTask.delay(
    author=request.user,
    param1='value1'
)

# With environment variables
task = DataProcessingTask.delay(
    envs={'MY_VAR': 'value'},
    param1='value1'
)
```

#### Synchronous Launch

```python
# Waits for task completion
task = DataProcessingTask.delay_sync(param1='value1')
```

### Periodic Tasks

#### Through Django Admin

1. Open "Periodic Tasks" section
2. Create new task:
   - **Name**: Task description
   - **Task Class**: Full path (e.g., `myapp.tasks.DataProcessingTask`)
   - **Period**: Cron expression or seconds
   - **Args/Kwargs**: JSON with parameters
   - **Enabled**: Yes

#### Period Examples

```python
# Every 60 seconds
period = "60"

# Every day at 03:00
period = "0 3 * * *"

# Every Monday at 09:00
period = "0 9 * * 1"

# Every hour
period = "0 * * * *"

# Every 5 minutes
period = "*/5 * * * *"
```

### Data Export

#### Base Export Class

```python
from bazis.contrib.bg.basic.base_download import BgBaseDownload

class ReportDownload(BgBaseDownload):
    name = 'Report Export'
    file_name = 'report'
    
    # Fields to export
    fields_read = ['id', 'name', 'created_at', 'status']
    
    # Fields marked bold in header
    fields_marked = {'name', 'status'}
    
    # Column sizes
    fields_size = {
        'id': 10,
        'name': 30,
        'created_at': 20,
        'status': 15
    }
    
    # Row limit per file (for splitting into archive)
    limit_rows_split = 500000
    
    def get_titles(self):
        """Returns column headers"""
        return {
            'id': 'ID',
            'name': 'Name',
            'created_at': 'Created At',
            'status': 'Status'
        }
    
    def get_queryset(self):
        """Returns data for export"""
        return MyModel.objects.all().values(*self.fields_read)
    
    def get_count(self):
        """Returns number of records"""
        return MyModel.objects.count()
```

#### Export with Grouped Headers

```python
def get_titles(self):
    return {
        'groups': [
            {
                'name_union': 'Basic Information',
                'columns': ['id', 'name'],
                'marked': True
            },
            {
                'name_union': 'Dates',
                'columns': ['created_at', 'updated_at']
            }
        ],
        'titles': {
            'id': 'ID',
            'name': 'Name',
            'created_at': 'Created',
            'updated_at': 'Updated'
        }
    }
```

#### Django Model Export

```python
from bazis.contrib.bg.basic.base_download_model import BgBaseDownloadModel
from django.apps import apps

class VehicleDownload(BgBaseDownloadModel):
    model = apps.get_model('myapp.Vehicle')
    fields_read = ['id', 'gnum', 'vehicle_model__brand__name', 'country__name']
    
    # verbose_name of fields will be picked up automatically
```

### Data Import

```python
from bazis.contrib.bg.basic.base_load import BgBaseLoad

class DataImport(BgBaseLoad):
    name = 'Data Import'
    
    # Fields in column order
    fields_read = ['name', 'price', 'quantity']
    
    # Skip first row (headers)
    skip_titles = True
    
    # Progress update period
    progress_count = 1000
    
    # Track row grouping
    groups_check = False
    
    # Add meta-data (_meta)
    with_meta = False
    
    def load(self, reader):
        """
        Process loaded data
        
        reader - generator of dictionaries with data
        """
        self.next_phase('Saving data')
        
        for row in reader:
            # row = {'name': '...', 'price': '...', 'quantity': '...'}
            
            # Create object
            MyModel.objects.create(
                name=row['name'],
                price=float(row['price']),
                quantity=int(row['quantity'])
            )
            
            self.progress(d_count=100)
```

## Task API

### Task Management Methods

```python
# Get task object
task = self.get_task()

# Update task data
self.task_update(
    phase='New phase',
    expected=1000,
    performed=500
)

# Save file in task
with open('result.xlsx', 'rb') as fp:
    self.task_file_save('result.xlsx', fp, file_params={'rows': 1000})

# Get file from task
fp = self.task_file_get()

# Set result
self.set_result({'status': 'success', 'count': 1000})

# Force synchronization
self.flush()
```

### Working with Phases

```python
# Simple phase
self.next_phase('Processing')

# Phase with expectation (number)
self.next_phase('Loading files', expected=100)

# Phase with expectation (dictionary)
self.next_phase('Processing', expected={
    'files': 10,
    'records': 1000
})

# Update progress
self.progress(
    performed=50,           # Performed
    expected=100,          # Expected (can be updated)
    d_time=5,              # Sync every 5 sec
    d_count=100,           # Or every 100 operations
    need_sync=True         # Force synchronization
)

# Progress with dictionary
self.progress(
    performed={'files': 5, 'records': 500},
    d_count=10
)
```

### Logging

```python
# Use self.log to write to task log
self.log.info('Information message')
self.log.warning('Warning')
self.log.error('Error')
self.log.debug('Debug information')

# Logs are automatically saved in task.log field
```

## Configuration

### Environment Variables

```bash
# Scheduler
BS_TASK_SCHEDULER_HOST=localhost  # Scheduler host
BS_TASK_SCHEDULER_PORT=8099       # Scheduler healthcheck port
BS_TASK_SCHEDULER_IDLE=1          # Delay between iterations, sec

# Handlers
BS_TASK_HANDLERS_LOCAL=3          # Number of local handlers
BS_TASK_HANDLER_PORT=8100         # Base port for handlers
BS_TASK_HANDLER_IDLE=1            # Delay between task checks, sec

# Storage
BS_TASK_FOLDER=bg/tasks           # Folder for task files
BS_STORAGE_BG=None                # Storage class (default FileSystemStorage)
```

### Django Settings

```python
# settings.py

# Number of local handlers
BAZIS_TASK_HANDLERS_LOCAL = 3

# Base port for handlers
BAZIS_TASK_HANDLER_PORT = 8100

# Scheduler task check interval (seconds)
BAZIS_TASK_SCHEDULER_IDLE = 1

# Handler task check interval (seconds)
BAZIS_TASK_HANDLER_IDLE = 1

# Custom storage for task files
BAZIS_STORAGE_BG = 'myapp.storage.S3Storage'
```

## Task Management

### Through Django Admin

1. **Background Tasks** (`Task`)
   - View all tasks
   - Filter by state, date
   - Interrupt running tasks
   - View logs and results
   - Download result files

2. **Periodic Tasks** (`TaskCron`)
   - Create/edit periodic tasks
   - Enable/disable
   - View next run time

3. **Handlers** (`TaskHandler`)
   - View active handlers
   - Monitor load

### Programmatically

```python
from django.apps import apps

Task = apps.get_model('bg.Task')

# Get task
task = Task.objects.get(id=task_id)

# Interrupt task
task.interrupt = True
task.save()

# Check state
if task.is_done:
    if task.is_success:
        print('Successfully completed')
    elif task.is_error:
        print(f'Error: {task.error}')
    elif task.is_interrupt:
        print('Interrupted')

# Get result
result = task.result

# Download file
if task.file:
    with task.file.open('rb') as fp:
        data = fp.read()
```

### Running Services

```bash
# Start scheduler
python manage.py bg_scheduler

# Start handler manually
python manage.py bg_handler --host 127.0.0.1 --port 8100

# In production, it's recommended to use supervisor or systemd
```

## Examples

### Example 1: Simple Task with Progress

```python
from bazis.contrib.bg.basic.base import BgBase

class SimpleTask(BgBase):
    name = 'Simple Task'
    
    def handle(self):
        self.next_phase('Processing', expected=100)
        
        for i in range(100):
            # Your logic
            self.log.info(f'Processing item {i+1}')
            self.progress(d_count=10)

# Launch
task = SimpleTask.delay()
```

### Example 2: Task with File

```python
from bazis.contrib.bg.basic.base import BgBase

class FileProcessingTask(BgBase):
    name = 'File Processing'
    
    def handle(self):
        # Get file
        fp = self.task_file_get()
        if not fp:
            raise Exception('File not provided')
        
        self.next_phase('Reading file')
        data = fp.read()
        
        # Processing...
        result = self.process_data(data)
        
        # Save result
        from io import BytesIO
        result_fp = BytesIO(result)
        self.task_file_save('result.txt', result_fp)
    
    def process_data(self, data):
        # Your processing logic
        return data.upper()

# Launch with file
with open('input.txt', 'rb') as fp:
    task = FileProcessingTask.delay(fp=fp)
```

### Example 3: Report Export

```python
from bazis.contrib.bg.basic.base_download_model import BgBaseDownloadModel
from django.apps import apps

class MonthlyReport(BgBaseDownloadModel):
    model = apps.get_model('myapp.Order')
    fields_read = ['id', 'number', 'customer__name', 'total', 'created_at']
    fields_marked = {'total'}
    file_name = 'monthly_report'

# Launch
task = MonthlyReport.delay()

# Get file after completion
from django.apps import apps
Task = apps.get_model('bg.Task')
task = Task.objects.get(id=task.id)
if task.is_success:
    file_url = task.file.url
```

### Example 4: Data Import

```python
from bazis.contrib.bg.basic.base_load import BgBaseLoad
from django.apps import apps

class ProductImport(BgBaseLoad):
    name = 'Product Import'
    fields_read = ['name', 'sku', 'price', 'quantity']
    skip_titles = True
    
    def load(self, reader):
        Product = apps.get_model('myapp.Product')
        
        self.next_phase('Importing products')
        
        created = 0
        updated = 0
        
        for row in reader:
            product, is_created = Product.objects.update_or_create(
                sku=row['sku'],
                defaults={
                    'name': row['name'],
                    'price': row['price'],
                    'quantity': row['quantity']
                }
            )
            
            if is_created:
                created += 1
            else:
                updated += 1
            
            self.progress(d_count=100)
        
        self.set_result({'created': created, 'updated': updated})

# Launch with file
with open('products.xlsx', 'rb') as fp:
    task = ProductImport.delay(fp=fp)
```

### Example 5: Task with Parameters

```python
from bazis.contrib.bg.basic.base import BgBase
from django.apps import apps

class SendEmailTask(BgBase):
    name = 'Send Email'
    parallel = 5  # Maximum 5 simultaneous sends
    
    def handle(self, email_list, subject, message):
        """
        Args:
            email_list: list of email addresses
            subject: email subject
            message: email body
        """
        self.next_phase('Sending emails', expected=len(email_list))
        
        for i, email in enumerate(email_list):
            try:
                # Send email
                self.send_email(email, subject, message)
                self.log.info(f'Sent to {email}')
            except Exception as e:
                self.log.error(f'Error sending to {email}: {e}')
            
            self.progress(performed=i+1, d_count=10)
    
    def send_email(self, email, subject, message):
        from django.core.mail import send_mail
        send_mail(subject, message, 'noreply@example.com', [email])

# Launch
emails = ['user1@example.com', 'user2@example.com']
task = SendEmailTask.delay(
    email_list=emails,
    subject='Important notification',
    message='Message text'
)
```

### Example 6: Task with Locks

```python
from bazis.contrib.bg.basic.base import BgBase

class DataExportTask(BgBase):
    name = 'Data Export'
    parallel = 1  # Only one task simultaneously
    blocked = [
        'myapp.tasks.DataImportTask',  # Blocked by import
        'myapp.tasks.DataUpdateTask'   # Blocked by update
    ]
    
    def handle(self):
        self.next_phase('Exporting data')
        # Export logic
        pass

class DataImportTask(BgBase):
    name = 'Data Import'
    parallel = 1
    blocked = [
        'myapp.tasks.DataExportTask',
        'myapp.tasks.DataUpdateTask'
    ]
    
    def handle(self):
        self.next_phase('Importing data')
        # Import logic
        pass
```

## Development

### Setting Up Development Environment

```bash
# Clone repository
git clone git@github.com:ecofuture-tech/bazis-bg.git
cd bazis-bg

# Install dependencies
uv sync --dev

# Run tests
pytest

# Check code
ruff check .

# Format code
ruff format .
```

### Test Structure

```
tests/
├── test_base.py              # Base class tests
├── test_download.py          # Export tests
├── test_load.py              # Import tests
├── test_scheduler.py         # Scheduler tests
└── test_handler.py           # Handler tests
```

## Contributing

We welcome your contributions! Here's how you can help:

1. Fork the repository
2. Create a branch for new functionality (`git checkout -b feature/amazing-feature`)
3. Make changes
4. Run tests (`pytest`)
5. Commit changes (`git commit -m 'Add amazing feature'`)
6. Push to branch (`git push origin feature/amazing-feature`)
7. Open Pull Request

Please ensure that:
- Tests are written for new functionality
- Documentation is updated
- Existing code style is maintained
- Changes are added to changelog

## License

Apache License 2.0

See [LICENSE](LICENSE) file for details.

## Links

- [Bazis Core](https://github.com/ecofuture-tech/bazis) — framework base package
- [Issue Tracker](https://github.com/ecofuture-tech/bazis-bg/issues) — report bug or request feature
- [Bazis Documentation](https://github.com/ecofuture-tech/bazis) — main documentation

## Support

If you have questions or problems:
- Check [documentation](https://github.com/ecofuture-tech/bazis)
- Search in [existing issues](https://github.com/ecofuture-tech/bazis-bg/issues)
- Create [new issue](https://github.com/ecofuture-tech/bazis-bg/issues/new) with detailed description

## Package Ecosystem

Bazis supports extensions through additional packages:

- `bazis` — framework core
- `bazis-bg` — background task system
- `bazis-test-utils` — testing utilities
- `bazis-<n>` — other extensions (add `bazis-` prefix to name)

All extension packages require installation of the base `bazis` package.

---

Made with ❤️ by Bazis team