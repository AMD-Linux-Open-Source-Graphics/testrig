# this isn't compliant with Fedora's packaging guidelines due to a naming
# collision in pypi with an existing testrig project.
# However, the package should work despite not being worth reviewing for
# inclusion in Fedora

Name:          testrig
Version:       0.0.7
Release:       1%{?dist}

Summary:       tool for running tests in a repeatable way
License:       MIT
BuildArch:     noarch


URL:           https://github.com/AMD-Linux-Open-Source-Graphics/testrig
Source0:        %{url}/archive/%{version}.tar.gz#/testrig-%{version}.tar.gz


BuildRequires: python3-devel
BuildRequires: python3-pytest
BuildRequires: python3-hatchling
BuildRequires: python3-docutils
BuildRequires: python3dist(pip)
BuildRequires: python3dist(packaging)

BuildRequires: python3-click
BuildRequires: gdb

%description
testrig is a tool for running tests in a repeatable way. it was written
primarily to provide a consistent interface to the ROCm component self tests
but might be useable in other places

%prep
%autosetup -p1 -n testrig-%{version}


%build
%pyproject_wheel
rst2man docs/manpage.rst > testrig.1


%install
%pyproject_install
#%pyproject_save_files testrig

mkdir -p %{buildroot}%{_mandir}/man1
install -pm 644 testrig.1* %{buildroot}%{_mandir}/man1

mkdir -p %{buildroot}%{_datadir}/%{name}
install -pm 644 support/gdb_traceback_on_stop.py %{buildroot}%{_datadir}/%{name}/gdb_traceback_on_stop.py

%files -f %{pyproject_files}
%{_mandir}/man1/*
%{_bindir}/%{name}
%{_datadir}/%{name}
%doc README.md


%changelog
* Mon Jul 20 2026 Tim Flink <tflink@fedoraproject.org> - 0.0.7-1
- move gdb-specific python file out of module

* Mon Jul 20 2026 Tim Flink <tflink@fedoraproject.org> - 0.0.6-1
- Initial release
